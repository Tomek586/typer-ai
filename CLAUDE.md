# Typer AI – zasady pracy w repozytorium

Dokumentacja projektu: `README.md` i `docs/`. Kod w pakiecie `typerai/`, testy w `tests/` (`.venv/Scripts/python -m pytest`).

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
