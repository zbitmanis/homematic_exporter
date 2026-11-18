# Fixture capture (spike tool, throwaway)

Closes intent Q2, Q3, Q5, Q7. Runs on your Mac; needs the internet and the access-point blue button.

```bash
brew install python@3.12                      # the Mac default `python3` is 3.9 and will NOT work
rm -rf .venv && "$(brew --prefix python@3.12)/bin/python3.12" -m venv .venv && . .venv/bin/activate
python --version                              # must print Python 3.12.x; stop if not
pip install -r requirements.txt
hmip_generate_auth_token                      # prompts: SGTIN, device name, PIN; press the blue button
# It writes ./config.ini (contains the token): it is git-ignored; delete it when done.
export HMIP_ACCESS_POINT=<SGTIN>  HMIP_AUTH_TOKEN=<token from config.ini>
python scripts/fixture/dump_state.py
```

Then open `tests/source/fixtures/state.summary.md` and `state.scrubbed.json`, check that no personal data remains (names are kept on purpose), and share the summary with Claude. Do not paste the token or SGTIN anywhere.

## Troubleshooting
- `Ignored the following versions that require a different python version` / `No matching distribution`: the venv is on an older Python (macOS default is 3.9). Delete `.venv`, recreate it with the explicit 3.12 path above, and check `python --version` first.
