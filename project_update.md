# cmux-remote-tui — Analiza inwestorska
_Model: owl | 2026-06-09 17:49 | 197s | korpus: 1 dokumentów_

# Analiza inwestorska: cmux-remote-tui

---

## FAZA 1 — TEZA

### Problem

Użytkownicy **cmux** (terminala zaprojektowanego dla coding agents — Claude Code, Hermes, itp.) mają maszynę deweloperską (desktop, Mac mini, serwer) uruchomioną gdzieś w pokoju, a sami siedzą z laptopem na kanapie lub w kawiarni. SSH daje dostęp do jednej powłoki, ale **nie daje topologii** — nie widać, który agent jest w którym workspace, co jest na każdym ekranie, nie można przełączać się między terminalami, nie można interaktywnie sterować TUI wewnątrz zdalnych terminalów (vim, menu, model pickery).

### Teza założycielska

Istnieje niewielki, ale realny segment deweloperów i power userów, którzy:
1. Używają cmux (lub podobnych terminalowych multi-agent orchestratorów) na zdalnej/dedykowanej maszynie
2. Chcą sterować tą maszyną z laptopa przez sieć (LAN lub Tailscale)
3. Potrzebują nie tylko podglądu, ale **interaktywnego attach** z pełnym przepływem klawiszy (ESC, Ctrl-*, Tab)

**Wartość:** Narzędzie eliminuje friction między "maszyna działa" a "mogę nią sterować z dowolnego miejsca". To nie jest problem milionów ludzi, to problem kilku-kilkunastu tysięcy power userów, którzy za to płacą za narzędzia.

### Why Now

- **Coding agents boom (2025-2026):** Claude Code, Aider, Codex, Hermes — każdy z nich działa w terminalu. Użytkownicy uruchamiają wiele agentów jednocześnie. cmux jest jednym z niewielu terminali zaprojektowanych pod ten use case.
- **Tailscale + remote dev:** Trend "beefy desktop at home, thin laptop everywhere else" przyspiesza. Tailscale robi sieć lokalną z każdego miejsca.
- **Brak konkurencji:** Nie istnieje dedykowany remote TUI dla cmux. Workaroundy (tmux + SSH, screen) nie dają topologii cmux ani attach z pełnym klawiszami.

### Kluczowe założenia i ocena ryzyka

| Założenie | Ryzyko | Uzasadnienie |
|---|---|---|
| cmux zyskuje/w utrzymuje bazę użytkowników | **WYSOKIE** | cmux to projekt jednej firmy (manaflow-ai). Jeśli cmux umrze, cmux-remote-tui umiera razem. Brak niezależnej wartości bez cmux. |
| Użytkownicy cmux faktycznie potrzebują remote access | **ŚREDNIE** | Wiele osób używa cmux lokalnie. Remote access to use case dla ~20-30% bazy? Trudno zweryfikować. |
| Tailscale/LAN setup jest wystarczająco prosty dla target user | **NISKI** | Target user to developer z SSH config i prawdopodobnie Tailscale. To nie jest problem. |
| "Zero dependencies" i prostota są konkurencyjną przewagą | **NISKI** | Agent to ~120 LOC stdlib Python. To jest feature, nie bug. |
| Można zbudować biznes wokół tego narzędzia | **WYSOKIE** | Patrz FAZA 4 — monetyzacja jest nieoczywista. |

---

## FAZA 2 — STAN OBECNY

### Co DZIAŁA teraz

Na podstawie README i kodu:

1. **Live topology** — lista workspace'ów, terminali, pane'ów, odświeżana w tle ✅
2. **Fuzzy find** — `/` + tekst, skok do terminala ✅
3. **Live preview** — podgląd ekranu wybranego terminala, real-time, side-by-side ✅
4. **Interactive attach** — `Enter` → fullscreen na terminal, klawisze przepływają (ESC, Ctrl-*, Tab), `Ctrl-]` detach ✅
5. **Zarządzanie workspace'ami** — focus, rename, create, close, move, pin, flash ✅
6. **`read all`** — dump wszystkich terminali naraz ✅
7. **Persistent agent** — ~120 LOC Python na remote host, trzyma socket cmux ciepłym, odpowiedzi ~0.1-0.2s na LAN ✅
8. **Zero dependencies** — stdlib only, Python 3 ✅
9. **Instalacja** — `install.sh <ssh-host>` kopiuje client + agent ✅
10. **CLI mode** — `cmux-remote ls`, `cmux-remote read all` ✅

### Co zaplanowane (z dokumentacji .planning)

Z dokumentacji `.planning` (GSD phase summaries) wynika, że projekt przeszedł fazę planowania i implementacji. Nie widzę w dokumentacji jasnych "planned but not implemented" feature'ów — to sugeruje, że **scope został zrealizowany** w granicach wyznaczonych w planie.

### ARCHITEKTURA

```
┌── laptop (local) ──────────┐         ┌── remote host ──────────────┐
│  cmux-remote (TUI)          │  one    │  agent.py ──► cmux CLI      │
│   ├─ UI thread (30fps)      │ persist │   (stdlib, ~120 LOC)        │
│   └─ worker thread ────────────SSH───►│   holds socket warm         │
└─────────────────────────────┘  pipe   └─────────────────────────────┘
```

**Kluczowa decyzja architektonczna:** Persistent agent na remote host zamiast "spawn ssh + cmux command" przy każdym requeście. To daje ~10x szybsze odpowiedzi (0.1-0.2s vs 1-2s).

**Kluczowy trick:** cmux pozwala `read`/`send` na dowolnym surface gdy caller jest z zewnątrz cmux (SSH). Agent wykorzystuje to do mirrorowania i sterowania terminalem.

### CORE MECHANISM

**Najważniejsza pętla działania:**

1. Worker thread → SSH pipe → agent.py → cmux CLI → JSON response
2. UI thread (30fps) renderuje listę + podgląd
3. User naciska `Enter` → attach mode → klawisze streamowane przez ten sam SSH pipe do cmux `send`
4. `Ctrl-]` → detach → powrót do listy

**Status: DZIAŁA.** To nie jest proof-of-concept — to działający produkt z install script, CLI mode i TUI.

### Dojrzałość

| Aspekt | Ocena | Uwagi |
|---|---|---|
| Funkcjonalność | **MVP+** | Core features działają, jest CLI mode, jest install script |
| Testy | **0%** | Zero testów. Żadnych. To największa luka. |
| CI/CD | **Brak** | Nie ma `.github/workflows`, nie ma Dockerfile |
| Dokumentacja | **Dobra** | README jest kompletne, z diagramami, install guide, usage |
| Tech debt | **Niskie** | 0.0/KLOC debt density, 949 LOC, 5 plików — to jest mikro |
| Bezpieczeństwo | **OK** | 0 secrets found, zero dependencies = zero supply chain risk |
| Onboarding | **Dobre** | `install.sh <ssh-host>` — jeden krok |

### Charakter pracy

- **1 autor** (vizi2000), 2 commity w ciągu 30 dni
- **949 LOC, 5 plików** — to jest mikro-projekt
- **Junior-mid developer profile** (z code metrics) — brak testów, ale niskie debt, zero dependencies, pragmatyczne podejście
- **AI-assisted signals: low** — kod wygląda na ręcznie pisany
- **Commit pattern: business hours** — 2 commity o 11:00

---

## FAZA 3 — PLAN

### Wizja

Dokumentacja nie zawiera jasno sformułowanej wizji długoterminowej. Z kontekstu wynika:

**Wizja implikowana:** "Najlepsze narzędzie do zdalnego sterowania cmux z dowolnego miejsca w sieci."

To jest **wąska, ale głęboka nisza** — nie "platforma", nie "ecosystem", ale "narzędzie, które robi jedną rzecz idealnie".

### Next milestone

Na podstawie stanu obecnego, logiczny next milestone to:

1. **Testy** — przynajmniej smoke tests dla agent.py i client.py
2. **CI** — GitHub Actions: lint, test, build
3. **Pakowanie** — pip installable (`pip install cmux-remote-tui`), nie tylko `install.sh`
4. **Multi-host** — obsługa wielu zdalnych hostów (config file zamiast jednego `$CMUX_REMOTE_HOST`)

### Luka stan → wizja

| Element luki | Priorytet | Opis |
|---|---|---|
| Brak testów | **P0** | Refactoring jest ryzykowny, correctness opiera się na manual checks |
| Brak CI | **P1** | Jeden developer, ale CI to safety net |
| Brak pip package | **P1** | `install.sh` działa, ale `pip install` to standard dla Python |
| Brak multi-host | **P2** | Power user może mieć 2-3 maszyny z cmux |
| Brak metrics/telemetry | **P2** | Nie wiesz, kto i jak używa narzędzia |
| Brak plugin system | **P3** | Długoterminowo: webhooks, notifications, integrations |

### Wiarygodność planu

**Niska.** Nie ma publicznego roadmap, nie ma milestone'ów w issues, nie ma timeline'u. Projekt jest w fazie "działa u autora, może działać u innych". To nie jest krytyczne dla narzędzia open-source, ale jest krytyczne dla inwestycji — nie ma jasnego planu rozwoju.

---

## FAZA 4 — WNIOSKI

### Mocne strony

1. **Zero dependencies** — agent to stdlib Python. Brak supply chain risk, brak upgrade hell. To jest **prawdziwa przewaga konkurencyjna** w świecie npm/pip dependency chaos.
2. **Core mechanism działa** — persistent agent + SSH pipe to eleganckie rozwiązanie. 0.1-0.2s response time na LAN.
3. **Mały, czytelny kod** — 949 LOC, 5 plików. Każdy może zrozumieć i zmodyfikować.
4. **README na poziomie** — diagramy, install guide, usage, "why" section. To nie jest afterthought.
5. **Niskie tech debt** — 0.0/KLOC. Autor nie zostawia rotu.
6. **Rozwiązuje realny problem** — remote access do cmux to nie jest wyimaginowany use case.

### Słabe strony

1. **Zero testów** — correctness opiera się na manual checks. Refactoring = ryzyko.
2. **Jedna maszyna docelowa** — tylko jeden `$CMUX_REMOTE_HOST`. Power user ma 2-3 maszyny.
3. **Brak CI/CD** — jeden developer, zero automation.
4. **Zależność od cmux** — jeśli manaflow-ai zmieni API cmux CLI, cmux-remote-tui się złamie. Brak abstraction layer.
5. **Brak publicznego roadmap** — nie wiesz, co będzie dalej.
6. **1 autor, 2 commity/30d** — to nie jest aktywny development, to jest "finished and parked".
7. **Brak metryk użycia** — nie wiesz, czy ktoś poza autorem tego używa.

### Moat

**Brak tradycyjnego moat.** Kod jest prosty (949 LOC), architektura jest oczywista (SSH pipe + JSON). Każdy średni developer może to odtworzyć w weekend.

**Potencjalny moat:**
- **Network effects w społeczności cmux** — jeśli stanie się "the way" to remotely control cmux
- **First-mover advantage** — nie ma konkurencji
- **Integration depth** — głębsza integracja z cmux (plugin API, events, notifications)

Ale żaden z tych moatów nie jest obecnie aktywny.

### Potencjał

**Niski-moderate.** To jest narzędzie dla wąskiej niszy (użytkownicy cmux, którzy potrzebują remote access). Nie ma ścieżki do "platformy" ani "ecosystemu" bez fundamentalnej zmiany scope.

**Scenariusz optymistyczny:** cmux zyskuje popularność → cmux-remote-tui staje się standardowym companion tool → community contributions → multi-host, web UI, mobile app.

**Scenariusz realistyczny:** cmux-remote-tui pozostaje narzędziem dla ~100-500 użytkowników, z których większość używa za darmo.

### Co zrobione (%)

**~70%** — core functionality działa, install script działa, README jest kompletne. Brakuje: testów, CI, pip package, multi-host, metrics, roadmap.

### Monetyzacja

**Uwaga krytyczna:** To jest open-source narzędzie dla deweloperów, rozwiązujące problem techniczny. Monetyzacja jest **nieoczywista**.

**Modele do rozważenia:**

| Model | Realizm | Uzasadnienie |
|---|---|---|
| **Open-core (free + paid features)** | Niski | Co mogłoby być paid? Multi-host? Web UI? Wąsko. |
| **SaaS companion (cloud relay)** | Średni | Cloud-based relay dla użytkowników bez Tailscale. Ale target user ma Tailscale. |
| **Donations / GitHub Sponsors** | Realistyczny | Standard dla OSS tools. Ale przy 100-500 users = €50-200/mo max. |
| **Enterprise license (cmux integration)** | Niski | Jeśli manaflow-ai chce oficjalnie wsparcie. Ale to wymaga traktowania z manaflow-ai. |
| **Paid support / consulting** | Realistyczny | "Pomogę ci skonfigurować remote cmux setup". Ale to nie skaluje. |

**TAM/SAM/SOM bottom-up:**

- **TAM (Total Addressable Market):** ~50,000-100,000 deweloperów używających terminal-based AI coding tools (Claude Code, Aider, Codex) na zdalnych maszynach. Ale to jest bardzo grube.
- **SAM (Serviceable Addressable Market):** ~5,000-10,000 użytkowników cmux (zakładając, że cmux ma ~10-20% market share wśród terminal-based AI tools).
- **SOM (Serviceable Obtainable Market):** ~100-500 użytkowników cmux, którzy potrzebują remote access i nie mają własnego rozwiązania.

**Realistyczny MRR po 12 miesiącach:** €0-500 (donations, może 1-2 płacących użytkowników za "pro" features jeśli zostaną zbudowane).

### Wycena

**As-is (bez inwestycji):** €5,000-15,000
- 949 LOC, działający produkt, zero testów, zero CI, 1 autor, brak roadmap
- Replacement cost: €4,160-11,440 (z code metrics)
- Premium za: działający product-market fit w mikro-niszy, zero dependencies, clean code

**Z inwestycją (jeśli autor buduje dalej):** €15,000-40,000
- Jeśli dodaje: testy, CI, pip package, multi-host, web UI, community building
- Ale to wymaga, że autor chce budować dalej

---

## TOP TODO

### P0 (must have)

1. **Dodać testy** — smoke tests dla agent.py i client.py. Bez tego refactoring jest ryzykowny.
2. **Dodać CI** — GitHub Actions: lint, test, build. Safety net dla jednego developera.

### P1 (should have)

3. **Pakowanie pip** — `pip install cmux-remote-tui` zamiast tylko `install.sh`. Standard dla Python.
4. **Multi-host support** — config file (`~/.config/cmux-remote/config.yaml`) z listą hostów, przełączanie między nimi.

### P2 (nice to have)

5. **Metryki użycia** — anonimowe telemetry (opt-in) lub przynajmniej GitHub stars tracking.
6. **Public roadmap** — GitHub Projects lub docs/ROADMAP.md.

---

```json
{
  "overall": 35,
  "tier": "nurture",
  "monetization_readiness": 10,
  "valuation_eur": {
    "as_is_low": 5000,
    "as_is_high": 15000
  },
  "mrr_eur": {
    "pessimistic": 0,
    "realistic": 100,
    "optimistic": 500,
    "arpa_eur_mo": 5,
    "customers_for_realistic": 20,
    "assumptions": "SOM ~100-500 użytkowników cmux z remote access need. ARPA oparte na GitHub Sponsors / donations (€5/mo) lub hipotetyczny 'pro' tier. Realistic = 20 płacących (2% conversion z 1000 users). Pessimistic = 0 (brak monetization effort). Optimistic = 500 (50 płacących × €10/mo, jeśli dodany pro tier z multi-host + web UI). MRR=0 jeśli autor nie buduje monetization path."
  },
  "todos": [
    {
      "title": "Dodać smoke tests dla agent.py i client.py",
      "priority": "P0",
      "effort": "M",
      "unlocks": "Bezpieczny refactoring, CI pipeline, confidence przy dodawaniu nowych feature'ów",
      "prompt": "W projekcie cmux-remote-tui (Python, 949 LOC, 5 plików, zero dependencies) dodaj smoke tests dla agent.py (remote agent ~120 LOC, shells out to cmux CLI, speaks newline-delimited JSON over SSH pipe) i client.py (TUI client z UI thread 30fps + worker thread). Użyj pytest lub unittest. Testy powinny: (1) mockować SSH pipe i cmux CLI responses, (2) walidować JSON parsing, (3) testować attach/detach flow, (4) testować error handling (broken pipe, timeout). Struktura: tests/ directory conftest.py z fixtures. Cel: minimum 5 testów, coverage >60% dla agent.py i client.py. Nie dodawaj zewnętrznych dependencies poza pytest."
    },
    {
      "title": "Dodać GitHub Actions CI pipeline",
      "priority": "P0",
      "effort": "S",
      "unlocks": "Automated testing przy każdym PR, safety net dla solo developera, credibility dla contributors",
      "prompt": "W projekcie cmux-remote-tui dodaj GitHub Actions workflow (.github/workflows/ci.yml) który: (1) run na push i PR do main, (2) setup Python 3.8+, (3) install dependencies (jeśli jakiekolwiek), (4) run lint (flake8 lub ruff), (5) run tests (pytest), (6) report coverage. Opcjonalnie: add badge do README. Plik: .github/workflows/ci.yml. Keep it simple — to jest mikro-projekt."
    },
    {
      "title": "Dodać pip installable package (pyproject.toml + setup)",
      "priority": "P1",
      "effort": "M",
      "unlocks": "Standardowa instalacja Python (`pip install cmux-remote-tui`), entry point CLI, distribution via PyPI w przyszłości",
      "prompt": "W projekcie cmux-remote-tui dodaj pełny pyproject.toml z: (1) [build-system] używający setuptools lub hatchling, (2) [project] z name='cmux-remote-tui', version, description, readme, license, python-requires='>=3.8', (3) [project.scripts] entry point: cmux-remote = cmux_remote_tui.client:main (dostosuj do rzeczywistej struktury), (4) [project.urls] z GitHub repo. Zapewnij że `pip install .` działa i `cmux-remote` command jest dostępny. Zachowaj kompatybilność z istniejącym install.sh."
    },
    {
      "title": "Dodać multi-host support z config file",
      "priority": "P1",
      "effort": "L",
      "unlocks": "Power users z 2-3 maszynami cmux mogą przełączać się między nami, zwiększa TAM",
      "prompt": "W projekcie cmux-remote-tui dodaj multi-host support: (1) Config file ~/.config/cmux-remote/config.yaml z listą hostów (nazwa, ssh_host, opcjonalnie label), (2) CLI flag `--host <name>` który wybiera host z config, (3) TUI keybinding (np. `h`) do przełączania między hostami, (4) Fallback do $CMUX_REMOTE_HOST env var jeśli brak config. Format config.yaml:\n```yaml\nhosts:\n  desk:\n    ssh_host: desk\n    label: 'Mac Mini (home)'\n  office:\n    ssh_host: user@10.0.0.5\n    label: 'Office server'\n```\nDodaj walidację config file i helpful error messages."
    },
    {
      "title": "Dodać publiczny roadmap (docs/ROADMAP.md)",
      "priority": "P2",
      "effort": "S",
      "unlocks": "Transparency dla community, przyciąga contributors, pokazuje kierunek rozwoju",
      "prompt": "W projekcie cmux-remote-tui stwórz docs/ROADMAP.md z: (1) Current state summary (co działa), (2) Short-term (next 3 months): testy, CI, pip package, multi-host, (3) Medium-term (3-6 months): web UI, mobile view, notifications, (4) Long-term vision: 'the standard companion tool for remote cmux control', (5) Contributing guidelines. Format: Markdown z checkboxami. Keep it honest — to jest solo project, nie startup."
    },
    {
      "title": "Dodać anonimowe telemetry (opt-in)",
      "priority": "P2",
      "effort": "M",
      "unlocks": "Dane o użyciu: ile użytkowników, które features są używane, jakie błędy występują. Kriteczne dla product decisions.",
      "prompt": "W projekcie cmux-remote-tui dodaj opt-in telemetry: (1) Config flag w ~/.config/cmux-remote/config.yaml: telemetry: enabled: false (default OFF), (2) Anonimowe events: app_start, host_connected, attach_used, error_type, (3) Dane: timestamp, event_type, app_version, OS (bez PII), (4) Endpoint: prosty HTTP POST do statycznego endpointa (np. GitHub Pages + Formspree, lub własny serwer), (5) CLI flag `--telemetry` i `--no-telemetry`, (6) Pierwszy launch: prompt 'Enable anonymous usage stats? (y/N)'. Ważne: GDPR-compliant, zero PII, easy to disable. Alternatywa: zamiast własnego serwera, użyj GitHub API do trackowania stars/forks jako proxy dla adoption."
    }
  ]
}
```