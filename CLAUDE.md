# Typer AI – zasady pracy w repozytorium

Dokumentacja projektu: `README.md` i `docs/`. Kod w pakiecie `typerai/`, testy w `tests/` (`.venv/Scripts/python -m pytest`).

## Wspólny kontekst (dwie osoby, trzy komputery)

- Projekt rozwijają dwie osoby, każda we własnym Claude Code. Wspólną pamięcią jest repozytorium – zasady w `CONTRIBUTING.md`.
- **Przed pracą nad zadaniem przeczytaj `docs/DZIENNIK.md`** – są tam podjęte decyzje, wyniki testów i otwarte sprawy.
- **Po ważnej decyzji lub ustaleniu dopisz wpis na górze `docs/DZIENNIK.md`** (data, decyzja, krótkie uzasadnienie) w tym samym commicie lub pull requeście.
- Harmonogram typów (`typerai.scheduler`) działa tylko na komputerze domowym. Na innych komputerach baza `data/typer.db` jest kopią do odczytu: nie uruchamiaj tam `typerai.pipeline stage1/stage2/settle`.

## Commit messages

- Język: **angielski**.
- Format: **Conventional Commits** – `<typ>: <opis w trybie rozkazującym>`, pierwsza linia do 72 znaków, bez kropki na końcu.
- Typy: `feat` (nowa funkcja), `fix` (poprawka błędu), `docs` (dokumentacja), `test` (testy), `refactor`, `chore` (konfiguracja, zależności).
- Opcjonalnie pusta linia i 1–3 zdania wyjaśnienia „co i dlaczego”.
- **Bez stopek typu `Co-Authored-By` i bez wzmianek o generowaniu przez AI.**

Przykład:

```
feat: add SofaScore collector for match statistics

Fetches xG, corners and cards through the browser because the API rejects plain HTTP requests.
```
