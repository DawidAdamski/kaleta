---
adr_id: "008"
title: "Prophet for Financial Forecasting"
status: accepted
---

# ADR-8: Prophet for Financial Forecasting

- **Decision**: Use Meta's Prophet library for time-series forecasting.
- **Rationale**: Prophet handles seasonality, holidays, and missing data well — making
  it a natural fit for forecasting monthly expenses, income trends, and budget projections.
  Simple API with Pydantic-friendly outputs.
- **Consequence**: Forecasting logic lives in `services/forecast_service.py`.
  Prophet is CPU-bound; runs in a thread pool via `asyncio.run_in_executor` to avoid
  blocking the async event loop.
