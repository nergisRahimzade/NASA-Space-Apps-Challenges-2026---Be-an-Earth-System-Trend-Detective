# ESD-D06-BE: a recipe for a box that runs the API the same way on any computer.
#   Build:  docker build -t esd-api .
#   Run:    docker run -p 8000:8000 --env-file .env esd-api
#   Check:  open http://localhost:8000/health

# 1. Start from a small Linux image that already has Python 3.12.
FROM python:3.12-slim

# 2. Copy in uv, the tool the team uses to install packages.
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv

WORKDIR /app

# 3. Install the libraries first, using only the files that list them.
#    Docker reuses this slow step on later builds unless these files change.
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --locked --no-dev --no-install-project

# 4. Copy our code and the mock results, then install the project itself.
COPY src ./src
COPY results.mock.json trend_map.mock.json ./
COPY results ./results
RUN uv sync --locked --no-dev


# 5. Start the API. Hosts such as Render say which port to use through PORT.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uv run --no-sync uvicorn earth_system_trend.api:app --host 0.0.0.0 --port ${PORT}"]
