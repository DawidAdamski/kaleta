# Product Requirements Document (PRD)
**Project Name:** Kaleta

## 1. App Info & Problem Statement
Kaleta is a personal finance management application designed to teach and facilitate budgeting, expense tracking, and cashflow forecasting. 
It solves the problem of financial chaos for users who manage multiple accounts, perform numerous internal transfers, and need a fast, frictionless tool to verify if they are staying within their planned budget.

## 2. Target Audience
Power users who actively manage their household budget, have a high volume of transactions ("more than an average stone"), and regularly move money between various accounts and banks. They expect a fast, productivity-oriented tool.

## 3. Success Criteria
- Users can smoothly import a batch of transaction data (e.g., CSV).
- Users can instantly add a single transaction using ONLY the keyboard (keyboard shortcuts).
- The application generates clear graphs and charts that instantly compare the planned budget with actual spending.

## 4. In Scope (MVP)
- **Budgeting Module:** Creating budgets for specific periods (e.g., monthly) broken down by categories.
- **Transaction Management:** 
  - Rapid manual entry optimized for keyboard use (shortcuts).
  - Data import mechanism (parsing standard bank CSV files).
- **Internal Transfers:** Intelligent and quick tagging of transfers between own accounts so they do not distort expense/income statistics.
- **Visualization & Reporting:** Dashboard with charts comparing the planned budget against actual consumption.
- **Basic Forecasting (Cashflow):** A simple view predicting the account balance based on the planned budget, fixed expenses, and historical trends (using Prophet).

## 5. Out of Scope
- Investment module (tracking stocks, crypto, bonds, capital gains) - deferred to later stages.
- Automatic bank synchronization via open API (PSD2) - MVP focuses on file imports and fast manual entry to keep architecture and security simple initially.
- Tax settlements and complex corporate accounting.

## 6. User Stories
1. **As a user**, I want to create a monthly budget by category, so I know exactly how much I can spend on specific goals.
2. **As a user**, I want to add a new expense in under 3 seconds using keyboard shortcuts, so I don't get frustrated by a slow interface.
3. **As a user**, I want to upload a CSV file with my account history, so I can mass-update my spending records.
4. **As a user**, I want to easily link an outflow from Account A with an inflow to Account B as an "Internal Transfer", so the system doesn't count it as an expense or income.
5. **As a user**, I want to see a clear bar/line chart showing my spending against the planned budget, so I can quickly assess if I need to cut back.