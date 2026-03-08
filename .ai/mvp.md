# MVP Implementation Plan: Kaleta

This document outlines the step-by-step technical implementation plan for the Minimum Viable Product (MVP) of Kaleta. 
Agents should implement these phases sequentially, asking for user review after completing each phase.

## Phase 1: Project Setup & Core Infrastructure
- Initialize the Python 3.13+ environment using `uv`.
- Set up the basic directory structure (e.g., `src/`, `tests/`, `.ai/`).
- Configure FastAPI and NiceGUI entry points.
- Set up SQLite database connection using async SQLAlchemy 2.0.
- Initialize Alembic and create the base migration configuration.

## Phase 2: Data Layer (Models & Schemas)
- Define SQLAlchemy models:
  - `Account` (id, name, balance, type)
  - `Category` (id, name, type: income/expense)
  - `Transaction` (id, account_id, category_id, amount, date, description, is_internal_transfer, linked_transaction_id)
  - `Budget` (id, category_id, amount, month, year)
- Create corresponding Pydantic v2 schemas for data validation.
- Generate and apply the initial Alembic migration.

## Phase 3: Core UI & Fast Data Entry (Keyboard First)
- Build the main NiceGUI layout (Navigation Sidebar, Header, Dashboard area).
- Implement the "Add Transaction" modal/form.
- **CRITICAL:** Implement global keyboard shortcuts (e.g., `Ctrl+N` or `Cmd+N` to open the form, arrow keys to navigate, `Enter` to submit) for lightning-fast manual entry.
- Build basic CRUD views for Accounts and Categories.

## Phase 4: CSV Import & Internal Transfers Logic
- Implement a file upload component in NiceGUI for CSV files.
- Write a parser to handle standard bank CSV formats (amount, date, description).
- Implement the business logic to detect and link "Internal Transfers" (e.g., an outflow from Account A matching an inflow to Account B within a specific timeframe).

## Phase 5: Budgeting & Visualization (Dashboard)
- Create a UI view to set and manage monthly budgets per category.
- Integrate charts (using NiceGUI's native chart components like ECharts or Plotly) to visualize:
  - Planned Budget vs. Actual Spending (Bar chart).
  - Monthly cashflow summary.

## Phase 6: Basic Forecasting (Prophet Integration)
- Integrate the `prophet` library.
- Create a forecasting service that takes historical transaction data and fixed budget costs to predict the account balance for the next 30-60 days.
- Add a "Forecast" chart to the main dashboard.
