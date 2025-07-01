
## Setup & Installation

**Prerequisites:**

* Python 3.8+
* pip (Python package installer)
* Optional: PostgreSQL server (if not using SQLite)

**Steps:**

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd backend # Navigate to the backend folder
    ```
2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # Linux/macOS
    # or
    .\venv\Scripts\activate # Windows
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Configure environment variables:**
    * Create a file called `.env` in the `backend` directory.
    * Add the database URL.
        * **For SQLite (default):**
            ```dotenv
            DATABASE_URL=sqlite+aiosqlite:///./survey_app.db
            ```
        * **For PostgreSQL (example):**
            ```dotenv
            DATABASE_URL=postgresql+asyncpg://DEIN_BENUTZER:DEIN_PASSWORT@localhost:5432/DEINE_DB
            ```
            (Replace the placeholders according to your PostgreSQL configuration).
5.  **Initialize the database (create tables):**
    * On the very first run or after changes to `models.py`, the database tables must be created.
    * **For development:** You can use the `create_db_and_tables` function in `database.py`. One approach is to run it manually once or briefly uncomment the line in the `lifespan` manager in `main.py` and start the server.
        ```python
        # In main.py, innerhalb von lifespan, vor yield:
        # await create_db_and_tables()
        ```
    * **IMPORTANT:** For later changes to the database structure in a production environment, you should use a migration tool such as **Alembic**!

## Start the application (development)

Run the following command in a terminal (inside the `backend` folder with the virtual environment activated):

```bash
uvicorn app.main:app --reload
```
## License

This project is licensed under the [MIT License](LICENSE).
