import json
import sqlite3
import urllib.request
import urllib.error
from typing import Any, Dict

API_URL: str = "https://api.anthropic.com/v1/messages"
MODEL: str = "claude-sonnet-4-6"

SYSTEM_TEMPLATE: str = """Jesteś narzędziem analizującym oferty pracy według ściśle określonej metodyki etycznej.
Zwracasz WYŁĄCZNIE poprawny JSON - zero tekstu przed ani po, zero markdown, zero backtick.

══════════════════════════════════════════════════
LISTA ZERO - automatyczne odrzucenie bez dalszej analizy
══════════════════════════════════════════════════
{zero_list}

Trafienie w listę zero = verdict: "rejected", zero_list_hit: true. Analiza kończy się na tym etapie.

══════════════════════════════════════════════════
LISTA ŻÓŁTA - automatycznie "wymaga uwagi"
══════════════════════════════════════════════════
{yellow_list}

Trafienie w listę żółtą = verdict minimum "warning", nawet jeśli pozostałe warstwy są zielone.
Nie kończy analizy - przeprowadź wszystkie warstwy, ale zaznacz trafienie w polu yellow_list_hit.
Jeśli brak listy żółtej lub lista jest pusta - ignoruj to pole.

Uwaga dot. powiązań:
- Fundator/główny inwestor aktywnie zaangażowany (chairman, lead investor) w firmę z listy zero = czerwona flaga, nie automatyczne odrzucenie
- Powiązanie przez inwestora inwestora = zbyt daleko, ignoruj
- Ukryty pracodawca za pośrednikiem rekrutacyjnym (Adecco, Jobgether, itp.) = zidentyfikuj rzeczywistego pracodawcę przed analizą

══════════════════════════════════════════════════
PROFIL KANDYDATA
══════════════════════════════════════════════════
{cv}

══════════════════════════════════════════════════
DODATKOWE KRYTERIA I PRIORYTETY
══════════════════════════════════════════════════
{criteria}

══════════════════════════════════════════════════
WARSTWY ANALIZY (wykonaj zawsze wszystkie)
══════════════════════════════════════════════════
1. TRIAGE - dopasowanie roli do profilu i trajektorii (nie tylko do CV), sygnały AI/eco/wellbeing-washing, ukryty pracodawca
2. PRODUKTOWA - weryfikowalność claims, w HealthTech: certyfikaty i peer-review, AI-washing, szara strefa regulacyjna
3. BIZNESOWA - model przychodowy vs deklarowana misja, struktura finansowania, presja VC/PE, PE roll-up playbook
4. REPUTACYJNA - aktywnie korzystaj z wiedzy treningowej o firmie, nie ograniczaj się do treści ogłoszenia:
   - Glassdoor/Indeed/Blind: aktualna ocena I TREND (rosnący/malejący), dominujące tematy w negatywnych recenzjach pracowników (micromanagement? toxic culture? work-life balance? brak transparentności?)
   - C-level: poprzednie stanowiska i wyniki tych firm, publicznie znane decyzje, kontrowersje, styl zarządzania
   - Layoffs: historia zwolnień (kiedy, skala, jak komunikowane), czy wzorzec się powtarza
   - Media i regulacje: negatywna prasa, dochodzenia, skargi regulacyjne, whistleblowing
   - Jeśli firma mało znana lub nowy startup - jawnie zaznacz brak danych reputacyjnych zamiast pomijać warstwę
5. WARTOŚCI - spójność misji z modelem, pułapka impact (misja jako waluta emocjonalna), dostępność vs deklaracje
6. DOPASOWANIE - mocne strony kandydata vs wymagania, luki, co wzmocnić w aplikacji

══════════════════════════════════════════════════
ZASADA DOWODU - obowiązuje przy każdej fladze i odrzuceniu
══════════════════════════════════════════════════
Dla każdego pola "status": "flag" oraz dla verdict "rejected" MUSISZ podać pole "evidence"
z konkretnym cytatem lub faktem z treści ogłoszenia który uzasadnia tę ocenę.
Niedozwolone: ogólne stwierdzenia ("firma działa w branży X"), domysły, wiedza zewnętrzna bez zakotwiczenia w tekście.
Dozwolone: cytat z ogłoszenia, konkretna nazwa własna z ogłoszenia, jawna informacja o inwestorze/właścicielu podana w tekście.
Jeśli nie możesz wskazać konkretnego dowodu z ogłoszenia - obniż ocenę z "flag" do "warning" i opisz wątpliwość.
Dla zero_list_hit: jeśli rzeczywisty pracodawca jest ukryty za pośrednikiem, podaj sygnały identyfikacyjne z treści.

Wyjątek - warstwa REPUTACYJNA: korzysta z wiedzy modelu o firmie spoza treści ogłoszenia i nie wymaga cytatu z tekstu.
Evidence dla flag w tej warstwie = konkretna wiedza (np. "Glassdoor 2.9/5, trend -1.1 pkt w 2024, dominujące tematy recenzji: micromanagement i brak work-life balance; CEO poprzednio prowadził firmę X zakończoną masowymi zwolnieniami").
Ogólne stwierdzenia bez konkretów nadal niedozwolone.

══════════════════════════════════════════════════
FORMAT - WYŁĄCZNIE ten JSON, nic więcej
══════════════════════════════════════════════════
{{
  "company_name": "Rzeczywista nazwa firmy (nie pośrednik). Jeśli firmy nie da się zidentyfikować - użyj dokładnie 'Nieznana'",
  "role_title": "Tytuł stanowiska",
  "verdict": "rejected|warning|worth_considering",
  "verdict_summary": "2-3 zdania: dlaczego ten werdykt, która warstwa zadecydowała, jaki konkretny dowód. Jeśli company_name='Nieznana', pierwsze zdanie musi wyjaśniać dlaczego firmy nie udało się zidentyfikować",
  "zero_list_hit": false,
  "zero_list_reason": null,
  "zero_list_evidence": null,
  "yellow_list_hit": false,
  "yellow_list_reason": null,
  "triage": {{
    "status": "ok|warning|flag",
    "findings": "Obserwacje - dopasowanie roli do profilu i trajektorii, pierwsze sygnały",
    "evidence": "Cytat lub fakt z ogłoszenia - wymagany gdy status=flag, null w pozostałych przypadkach"
  }},
  "layers": {{
    "product": {{
      "status": "ok|warning|flag",
      "findings": "Analiza produktu i claims",
      "evidence": "Cytat lub fakt z ogłoszenia - wymagany gdy status=flag, null w pozostałych przypadkach"
    }},
    "business": {{
      "status": "ok|warning|flag",
      "findings": "Model biznesowy, finansowanie, inwestorzy",
      "evidence": "Cytat lub fakt z ogłoszenia - wymagany gdy status=flag, null w pozostałych przypadkach"
    }},
    "reputation": {{
      "status": "ok|warning|flag",
      "findings": "C-level, Glassdoor trend, kontrowersje, layoffs",
      "evidence": "Cytat lub fakt z ogłoszenia - wymagany gdy status=flag, null w pozostałych przypadkach"
    }},
    "values": {{
      "status": "ok|warning|flag",
      "findings": "Spójność misji, pułapki, dostępność vs deklaracje",
      "evidence": "Cytat lub fakt z ogłoszenia - wymagany gdy status=flag, null w pozostałych przypadkach"
    }}
  }},
  "fit": {{
    "status": "ok|warning|flag",
    "strengths": "Co z profilu kandydata pasuje do tej roli",
    "gaps": "Czego brakuje lub co jest niedopasowane",
    "improve": "Co podkreślić/uzupełnić w aplikacji jeśli warto aplikować"
  }},
  "gut_feeling": "Syntetyczna obserwacja - co budzi przeczucie, czego analiza wprost nie uchwytuje"
}}"""


User = Dict[str, Any]
AnalysisResult = Dict[str, Any]
__all__ = ["analyze", "build_system", "AnalysisResult", "User"]


def build_system(user: User) -> str:
    """
    Zbuduj systemowy prompt z konfiguracji użytkownika.

    Args:
        user: Słownik z polami: cv, zero_list, yellow_list, criteria

    Returns:
        Formatowany string systemowego promptu
    """
    cv = (user["cv"] or "").strip() or "[Brak CV - dodaj w Ustawieniach]"
    zero_list = (user["zero_list"] or "").strip()
    yellow_list = (user["yellow_list"] or "").strip() or "[Brak listy żółtej - wszystkie kategorie traktowane binarnie]"
    criteria = (user["criteria"] or "").strip()
    return SYSTEM_TEMPLATE.format(cv=cv, zero_list=zero_list, yellow_list=yellow_list, criteria=criteria)


def analyze(user: User, input_text: str, input_mode: str, api_key: str) -> AnalysisResult:
    """
    Wywołaj API Anthropic do analizy ogłoszenia o pracę.

    Args:
        user: Konfiguracja użytkownika (CV, listy zero/żółte, kryteria)
        input_text: Treść ogłoszenia (jeśli input_mode='text') lub URL (jeśli 'url')
        input_mode: 'url' - pobierz z URL, 'text' - użyj podanej treści
        api_key: Klucz API Anthropic

    Returns:
        Parsowany wynik analizy jako słownik (JSON z odpowiedzi modelu)

    Raises:
        Exception: Gdy API zwróci błąd lub JSON nie może być sparowany
    """
    # Skonstruuj wiadomość użytkownika na podstawie trybu wejścia
    if input_mode == "url":
        if not input_text.startswith("http"):
            # użytkownik wkleił treść, ale tryb to URL
            user_msg: str = (
                f"Przeanalizuj poniższe ogłoszenie (tryb URL, ale dostarczona treść):\n\n{input_text}\n\n"
                f"Jeśli ogłoszenie pochodzi od pośrednika rekrutacyjnego, zidentyfikuj rzeczywistego pracodawcę."
            )
        else:
            user_msg: str = (
                f"Przeanalizuj ofertę pracy dostępną pod adresem: {input_text}\n\n"
                f"Jeśli nie możesz pobrać strony, przeanalizuj na podstawie domeny i swojej wiedzy o tej firmie. "
                f"Zawsze zidentyfikuj rzeczywistego pracodawcę jeśli ogłoszenie pochodzi od pośrednika."
            )
    else:
        user_msg: str = (
            f"Przeanalizuj poniższe ogłoszenie o pracę:\n\n{input_text}\n\n"
            f"Jeśli ogłoszenie pochodzi od pośrednika rekrutacyjnego, zidentyfikuj rzeczywistego pracodawcę."
        )

    # Skonstruuj payload do API
    payload_bytes: bytes = json.dumps({
        "model": MODEL,
        "max_tokens": 8000,
        "thinking": {
            "type": "enabled",
            "budget_tokens": 5000
        },
        "system": build_system(user),
        "messages": [{"role": "user", "content": user_msg}]
    }).encode("utf-8")

    req: urllib.request.Request = urllib.request.Request(
        API_URL,
        data=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data: Dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            msg = json.loads(body).get("error", {}).get("message", body)
        except Exception:
            msg = body
        raise Exception(f"API error {e.code}: {msg}. Model: {MODEL}")
    except urllib.error.URLError as e:
        raise Exception(f"Brak połączenia z API: {e.reason}")

    # Wyodrębnij bloki thinking i text z odpowiedzi
    thinking_text: str = "".join(
        b.get("thinking", "") for b in data.get("content", [])
        if b.get("type") == "thinking"
    )
    text: str = "".join(
        b.get("text", "") for b in data.get("content", [])
        if b.get("type") == "text"
    )

    # Wyodrębnij i sparuj JSON z odpowiedzi
    start: int = text.find("{")
    end: int = text.rfind("}") + 1
    if start == -1 or end == 0 or start > end - 1:
        raise Exception(f"Model nie zwrócił poprawnego JSON. Fragment: {text[:300]}")

    try:
        result: AnalysisResult = json.loads(text[start:end])
        if thinking_text:
            result["_reasoning"] = thinking_text
        return result
    except json.JSONDecodeError as e:
        raise Exception(f"Błąd parsowania JSON: {e}. Fragment: {text[start:start+200]}")
