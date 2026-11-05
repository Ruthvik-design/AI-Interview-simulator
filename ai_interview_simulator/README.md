# AI Adaptive Interview Simulator (modular)

## Run
1. Install Python 3.9+ (no third-party Python packages required).
2. Install/start Ollama and run `ollama pull llama3.2`.
3. From this directory run `python main.py`.
4. Open http://127.0.0.1:8000.

Default admin: `admin` / `admin123`. Set `ADMIN_PASSWORD` before first run and change the default in production.

## Modules
- `agents/`: AI interview agents and improvement coach.
- `prompts/`: editable default system prompts.
- `services/`: Ollama integration and progress tracking.
- `database.py`: SQLite schema, migrations, and persistence.
- `routes.py`: HTTP API and request handling.
- `templates.py`: browser UI.
- `config.py`: environment-based configuration.

The database file defaults to `interview_simulator.db` in this project directory. To keep an existing database from the single-file version, set `INTERVIEW_DB` to its full path before launching; the app will upgrade its schema in place.
