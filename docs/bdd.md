# Kaleta — BDD Scenarios (Gherkin)

All scenarios run against a live Kaleta instance at `http://localhost:8080`.
The app must be started before the scenario suite runs.
Each scenario uses a fresh isolated database (see `tests/e2e/conftest.py`).

Scenarios are organised around the **user workflows** Kaleta exists to
support — the rhythm of actually running one's personal finances — rather
than around UI pages:

| Workflow | Cadence | What the user is doing |
|---|---|---|
| 1. Set up the ledger | once / rarely | institutions, accounts, categories, tags, payees |
| 2. Capture transactions | daily / weekly / monthly | manual entry, splits, CSV import, transfer recognition, auto-categorisation |
| 3. Monthly cycle | monthly | close last month, plan next month, compare, recurring payments, subscriptions |
| 4. Annual cycle | yearly | annual review, irregular expenses fund, gift planning |
| 5. Funds and goals | ongoing | sinking funds (skarbonki), emergency and security reserves |
| 6. Insight | ongoing | forecast, credit, debts, investments, AI summaries |
| 7. Platform | — | authentication, data safety, public API |

Scenario tags:

- `@automated` — implemented and covered by an e2e/integration test
  (enforced by `scripts/spec_coverage.py` in CI).
- `@manual` — implemented, verified by hand.
- `@planned` — **specified but not yet implemented**; these scenarios
  are the product backlog in executable form. When a planned feature
  ships, retag its scenarios `@automated`/`@manual` and add tests.


---

# Workflow 1 — Set up the ledger

Run rarely: shape the ledger so daily capture is effortless later.

## Feature: Initial Setup Wizard

```gherkin
Feature: Initial Setup Wizard
  As a new user
  I want to be guided step by step through the initial configuration
  So that I can start tracking my full financial picture from day one
  with every zloty assigned to a purpose (zero-based budget approach)

  # --- Wizard entry ---

  KAL-SET-001 @manual
  Scenario: Fresh installation redirects to Setup wizard
    Given the database is empty
    When I open the application
    Then I am redirected to the Setup page
    And I see a welcome message explaining the zero-based budgeting approach
    And I see the list of setup steps to complete

  KAL-SET-002 @manual
  Scenario: Returning user skips wizard if setup is complete
    Given the setup wizard has been completed
    When I open the application
    Then I land on the main Dashboard page
    And I do not see the setup wizard

  # --- Step 1: Add first institution ---

  KAL-SET-003 @manual
  Scenario: Wizard step 1 — add an institution
    Given I am on the Setup wizard at step "Institution"
    When I fill in "Name" with "PKO Bank Polski"
    And I select type "Bank"
    And I click "Save and continue"
    Then step "Institution" is marked as complete
    And I advance to step "Accounts"

  # --- Step 2: Add accounts with opening balances ---

  KAL-SET-004 @manual
  Scenario: Wizard step 2 — add an account with opening balance
    Given I am on the Setup wizard at step "Accounts"
    When I click "Add Account"
    And I fill in "Name" with "PKO Main"
    And I fill in "Currency" with "PLN"
    And I fill in "Opening Balance" with "5000"
    And I click "Save"
    Then "PKO Main" appears in the accounts list with opening balance "5000 PLN"

  KAL-SET-005 @manual
  Scenario: Wizard step 2 — add multiple accounts
    Given I am on the Setup wizard at step "Accounts"
    When I add account "PKO Main" with opening balance "5000"
    And I add account "Cash Wallet" with opening balance "300"
    And I add account "mBank Savings" with opening balance "20000"
    And I click "Continue"
    Then all three accounts are saved
    And total funds to assign show "25300 PLN"
    And I advance to step "Categories"

  # --- Step 3: Set up categories ---

  KAL-SET-006 @manual
  Scenario: Wizard step 3 — set up expense categories
    Given I am on the Setup wizard at step "Categories"
    When I add expense categories "Food", "Transport", "Housing", "Entertainment"
    And I add income categories "Salary", "Freelance"
    And I click "Continue"
    Then the categories are saved
    And I advance to step "Budget"

  KAL-SET-007 @manual
  Scenario: Wizard step 3 — use suggested default categories
    Given I am on the Setup wizard at step "Categories"
    When I click "Load suggested categories"
    Then a predefined set of common expense and income categories is loaded
    And I can remove or rename any of them before continuing

  # --- Step 4: Assign all money to budget (zero-based) ---

  KAL-SET-008 @manual
  Scenario: Wizard step 4 — assign all opening balance to budget categories
    Given I am on the Setup wizard at step "Budget"
    And the total unassigned funds are "25300 PLN"
    When I assign "5000" to "Housing"
    And I assign "2000" to "Food"
    And I assign "18300" to "Savings"
    Then the unassigned amount shows "0 PLN"
    And a "Every zloty is assigned" confirmation is displayed
    And I can click "Finish Setup"

  KAL-SET-009 @manual
  Scenario: Wizard step 4 — cannot finish with unassigned money
    Given I am on the Setup wizard at step "Budget"
    And the total unassigned funds are "25300 PLN"
    When I assign only "20000" across categories
    Then the unassigned amount shows "5300 PLN"
    And the "Finish Setup" button is disabled
    And I see a message "5,300.00 PLN still needs to be assigned"

  KAL-SET-010 @manual
  Scenario: Wizard step 4 — cannot over-assign more than available funds
    Given the total unassigned funds are "25300 PLN"
    And I am on the Setup wizard at step "Budget"
    When I try to assign "30000" across categories
    Then I see a validation error "Total assigned exceeds available funds"

  # --- Finishing setup ---

  KAL-SET-011 @manual
  Scenario: Completing all steps marks setup as done
    Given I have completed all wizard steps
    When I click "Finish Setup"
    Then I am redirected to the main Dashboard
    And the dashboard shows my accounts with balances
    And the budget overview reflects my initial assignments

  KAL-SET-012 @manual
  Scenario: Resume incomplete setup from wizard page
    Given I completed steps "Institution" and "Accounts" but not "Categories"
    When I navigate to the Setup page
    Then I see steps "Institution" and "Accounts" marked as complete
    And step "Categories" is highlighted as the current step
    And I can continue from where I left off
```

## Feature: Onboarding Wizard

```gherkin
Feature: Onboarding Wizard
  As a new user
  I want to be guided through initial setup
  So that I can start tracking finances quickly

  KAL-ONB-001 @automated
  Scenario: Wizard shows incomplete steps for a fresh database
    Given the database is empty
    And I am on the Financial Wizard page
    Then I see the "Na start" onboarding section
    And step "Add an institution" is marked as pending
    And step "Add an account" is marked as pending
    And step "Set up categories" is marked as pending
    And step "Import or add transactions" is marked as pending

  KAL-ONB-002 @automated
  Scenario: Wizard marks steps as done as data is added
    Given I have added an institution and an account
    And I am on the Financial Wizard page
    Then step "Add an institution" is marked as done
    And step "Add an account" is marked as done
    And step "Set up categories" is marked as pending
```

## Feature: Institution Management

```gherkin
Feature: Institution Management
  As a user
  I want to manage financial institutions
  So that I can organise my accounts by the bank or provider they belong to

  KAL-INS-001 @automated
  Scenario: Add a new institution
    Given I am on the Institutions page
    When I click "Add Institution"
    And I fill in "Name" with "PKO Bank Polski"
    And I select type "Bank"
    And I click "Save"
    Then I see "PKO Bank Polski" in the institutions list

  KAL-INS-002 @manual
  Scenario: Add an institution with optional fields
    Given I am on the Institutions page
    When I click "Add Institution"
    And I fill in "Name" with "mBank"
    And I select type "Bank"
    And I fill in "Website" with "https://www.mbank.pl"
    And I fill in "Description" with "Main everyday account"
    And I pick a colour
    And I click "Save"
    Then I see "mBank" in the institutions list

  KAL-INS-003 @automated
  Scenario: Edit an existing institution
    Given there is an institution "PKO Bank Polski"
    And I am on the Institutions page
    When I click the edit button for "PKO Bank Polski"
    And I change "Name" to "PKO BP"
    And I click "Save"
    Then I see "PKO BP" in the institutions list
    And I do not see "PKO Bank Polski"

  KAL-INS-004 @automated
  Scenario: Delete an institution with no linked accounts
    Given there is an institution "Old Bank" with no accounts
    And I am on the Institutions page
    When I click the delete button for "Old Bank"
    And I confirm deletion
    Then "Old Bank" is no longer in the institutions list

  KAL-INS-005 @manual
  Scenario: Delete an institution that has linked accounts
    Given there is an institution "PKO BP" with at least one linked account
    And I am on the Institutions page
    When I click the delete button for "PKO BP"
    And I confirm deletion
    Then "PKO BP" is no longer in the institutions list
    And the previously linked accounts still exist without an institution reference

  KAL-INS-006 @automated
  Scenario: Cannot add an institution without a name
    Given I am on the Institutions page
    When I click "Add Institution"
    And I leave "Name" empty
    And I click "Save"
    Then I see a validation error
    And no institution is created

  KAL-INS-007 @manual
  Scenario: Cannot add two institutions with the same name
    Given there is an institution "mBank"
    And I am on the Institutions page
    When I try to add another institution named "mBank"
    Then I see a duplicate name error
    And only one "mBank" entry exists in the list

  KAL-INS-008 @manual
  Scenario: Institution type defaults to Bank
    Given I am on the Institutions page
    When I click "Add Institution"
    Then the "Type" field defaults to "Bank"
```

## Feature: Account Management

```gherkin
Feature: Account Management
  As a user
  I want to manage my bank accounts
  So that I can track money across multiple accounts

  KAL-ACC-001 @automated
  Scenario: Add a new account
    Given I am on the Accounts page
    When I click "Add Account"
    And I fill in "Name" with "PKO Main"
    And I fill in "Currency" with "PLN"
    And I click "Save"
    Then I see "PKO Main" in the accounts list

  KAL-ACC-002 @automated
  Scenario: Edit an existing account
    Given there is an account "PKO Main"
    And I am on the Accounts page
    When I click the edit button for "PKO Main"
    And I change "Name" to "PKO Personal"
    And I click "Save"
    Then I see "PKO Personal" in the accounts list
    And I do not see "PKO Main"

  KAL-ACC-003 @automated
  Scenario: Delete an account
    Given there is an account "Old Account"
    And I am on the Accounts page
    When I click the delete button for "Old Account"
    And I confirm deletion
    Then I do not see "Old Account" in the accounts list

  KAL-ACC-004 @automated
  Scenario: Cannot add account without a name
    Given I am on the Accounts page
    When I click "Add Account"
    And I leave "Name" empty
    And I click "Save"
    Then I see a validation error
    And the account is not created
```

## Feature: Category Management

```gherkin
Feature: Category Management
  As a user
  I want to organise transactions into categories
  So that I can analyse my spending

  KAL-CAT-001 @automated
  Scenario: Add a root expense category
    Given I am on the Categories page
    When I click "Add Category" in the Expense section
    And I fill in "Name" with "Food"
    And I click "Save"
    Then I see "Food" in the expense categories list

  KAL-CAT-002 @manual
  Scenario: Add a subcategory under an existing parent
    Given there is an expense category "Food"
    And I am on the Categories page
    When I click "Add Category" in the Expense section
    And I fill in "Name" with "Groceries"
    And I select "Food" as the parent
    And I click "Save"
    Then I see "Food → Groceries" in the expense categories list

  KAL-CAT-003 @automated
  Scenario: Edit a category name
    Given there is an expense category "Food"
    And I am on the Categories page
    When I click the edit button for "Food"
    And I change "Name" to "Groceries & Food"
    And I click "Save"
    Then I see "Groceries & Food" in the expense categories list
    And I do not see "Food" as a root category

  KAL-CAT-004 @manual
  Scenario: Edit a category moves it to a different parent
    Given there is an expense category "Food"
    And there is an expense category "Shopping"
    And there is a subcategory "Groceries" under "Food"
    And I am on the Categories page
    When I click the edit button for "Food → Groceries"
    And I select "Shopping" as the parent
    And I click "Save"
    Then I see "Shopping → Groceries" in the expense categories list
    And I do not see "Food → Groceries"
    And all transactions previously in "Food → Groceries" are now in "Shopping → Groceries"

  KAL-CAT-005 @manual
  Scenario: Promote a subcategory to root
    Given there is an expense category "Food"
    And there is a subcategory "Groceries" under "Food"
    And I am on the Categories page
    When I click the edit button for "Food → Groceries"
    And I clear the parent field
    And I click "Save"
    Then I see "Groceries" as a root expense category
    And all transactions previously in "Food → Groceries" remain linked to "Groceries"

  KAL-CAT-006 @manual
  Scenario: Delete a leaf category with no transactions
    Given there is an expense category "Food"
    And there is a subcategory "Snacks" under "Food" with no transactions
    And I am on the Categories page
    When I click the delete button for "Food → Snacks"
    And I confirm deletion
    Then "Snacks" is no longer in the categories list

  KAL-CAT-007 @automated
  Scenario: Delete a category that has transactions
    Given there is an expense category "Food" with linked transactions
    And I am on the Categories page
    When I click the delete button for "Food"
    And I confirm deletion
    Then "Food" is no longer in the categories list
    And the previously linked transactions still exist with no category

  KAL-CAT-008 @manual
  Scenario: Delete a parent category also removes its children
    Given there is an expense category "Food"
    And there is a subcategory "Groceries" under "Food"
    And I am on the Categories page
    When I click the delete button for "Food"
    And I confirm deletion
    Then "Food" is no longer in the categories list
    And "Groceries" is no longer in the categories list

  KAL-CAT-009 @manual
  Scenario: Two subcategories with the same name under different parents
    Given there is an expense category "Food"
    And there is an expense category "Transport"
    And I am on the Categories page
    When I add subcategory "Other" under "Food"
    And I add subcategory "Other" under "Transport"
    Then I see "Food → Other" in the categories list
    And I see "Transport → Other" in the categories list

  KAL-CAT-010 @manual
  Scenario: Cannot add two root categories with the same name
    Given there is an expense category "Food"
    And I am on the Categories page
    When I try to add another expense category named "Food" without a parent
    Then I see a duplicate name error

  KAL-CAT-011 @automated
  Scenario: Categories page renders the subscription category tree
    Given the database includes the Subscriptions root with subcategories
    When I open the Categories page
    Then I see "Subscriptions" in the expense categories list
    And I see "Monthly" as a subcategory under "Subscriptions"
    And I see "Yearly" as a subcategory under "Subscriptions"
    And I see "Other" as a subcategory under "Subscriptions"
```

## Feature: Tag Management

```gherkin
Feature: Tag Management
  As a user
  I want to create, edit, and remove tags
  So that I can label transactions with cross-cutting topics (e.g. "vacation", "business")

  KAL-TAG-001 @manual
  Scenario: Add a tag
    Given I am on the Tags page
    When I click "Add Tag"
    And I fill in "Name" with "Vacation"
    And I pick a colour
    And I click "Save"
    Then I see "Vacation" in the tags list

  KAL-TAG-002 @manual
  Scenario: Add a tag with all optional fields
    Given I am on the Tags page
    When I click "Add Tag"
    And I fill in "Name" with "Business"
    And I fill in "Description" with "Work-related expenses"
    And I fill in "Icon" with "work"
    And I pick a colour
    And I click "Save"
    Then I see "Business" in the tags list with the correct colour and icon

  KAL-TAG-003 @manual
  Scenario: Edit a tag name
    Given there is a tag "Vacation"
    And I am on the Tags page
    When I click the edit button for "Vacation"
    And I change "Name" to "Holiday"
    And I click "Save"
    Then I see "Holiday" in the tags list
    And I do not see "Vacation"

  KAL-TAG-004 @manual
  Scenario: Edit tag colour and description
    Given there is a tag "Business"
    And I am on the Tags page
    When I click the edit button for "Business"
    And I change the colour
    And I change "Description" to "All business travel"
    And I click "Save"
    Then the tag "Business" shows the updated colour and description

  KAL-TAG-005 @manual
  Scenario: Delete a tag
    Given there is a tag "OldTag"
    And I am on the Tags page
    When I click the delete button for "OldTag"
    And I confirm deletion
    Then "OldTag" is no longer in the tags list

  KAL-TAG-006 @manual
  Scenario: Deleting a tag does not delete linked transactions
    Given there is a tag "Vacation"
    And there are transactions tagged with "Vacation"
    And I am on the Tags page
    When I click the delete button for "Vacation"
    And I confirm deletion
    Then "Vacation" is no longer in the tags list
    And the previously tagged transactions still exist without that tag

  KAL-TAG-007 @manual
  Scenario: Cannot add two tags with the same name
    Given there is a tag "Vacation"
    And I am on the Tags page
    When I try to add another tag named "Vacation"
    Then I see a duplicate name error
    And only one "Vacation" entry exists in the list

  KAL-TAG-008 @manual
  Scenario: Cannot add a tag without a name
    Given I am on the Tags page
    When I click "Add Tag"
    And I leave "Name" empty
    And I click "Save"
    Then I see a validation error
    And no tag is created
```

## Feature: Payee Management

```gherkin
Feature: Payee Management
  As a user
  I want to manage payees with full contact details and merge duplicates
  So that I can keep my payee list clean and enriched with useful information

  KAL-PAY-001 @automated
  Scenario: Add a payee with name only
    Given I am on the Payees page
    When I click "Add Payee"
    And I fill in "Name" with "Biedronka"
    And I click "Save"
    Then I see "Biedronka" in the payees list

  KAL-PAY-002 @manual
  Scenario: Add a payee with all contact fields
    Given I am on the Payees page
    When I click "Add Payee"
    And I fill in "Name" with "ORLEN SA"
    And I fill in "Website" with "https://www.orlen.pl"
    And I fill in "Address" with "ul. Chemików 7"
    And I fill in "City" with "Płock"
    And I fill in "Country" with "Poland"
    And I fill in "Email" with "kontakt@orlen.pl"
    And I fill in "Phone" with "+48 800 080 080"
    And I fill in "Notes" with "Main fuel supplier"
    And I click "Save"
    Then I see "ORLEN SA" in the payees list
    When I open the detail view for "ORLEN SA"
    Then I see all the filled-in contact fields

  KAL-PAY-003 @automated
  Scenario: Edit a payee name
    Given there is a payee "BIEDRONKA SP Z OO"
    And I am on the Payees page
    When I click the edit button for "BIEDRONKA SP Z OO"
    And I change "Name" to "Biedronka"
    And I click "Save"
    Then I see "Biedronka" in the payees list

  KAL-PAY-004 @manual
  Scenario: Edit payee contact details
    Given there is a payee "Biedronka" with no contact details
    And I am on the Payees page
    When I click the edit button for "Biedronka"
    And I fill in "Address" with "ul. Różana 1"
    And I fill in "City" with "Inowrocław"
    And I fill in "Website" with "https://www.biedronka.pl"
    And I click "Save"
    Then the payee "Biedronka" shows the updated address and website

  KAL-PAY-005 @automated
  Scenario: Delete a payee
    Given there is a payee "OLD PAYEE"
    And I am on the Payees page
    When I click the delete button for "OLD PAYEE"
    And I confirm deletion
    Then "OLD PAYEE" is no longer in the payees list

  KAL-PAY-006 @manual
  Scenario: Deleting a payee does not delete linked transactions
    Given there is a payee "Biedronka" with linked transactions
    And I am on the Payees page
    When I click the delete button for "Biedronka"
    And I confirm deletion
    Then "Biedronka" is no longer in the payees list
    And the previously linked transactions still exist with no payee

  KAL-PAY-007 @automated
  Scenario: Merge duplicate payees
    Given there are payees "ORLEN SA" and "ORLEN STACJA 401"
    And both have linked transactions
    And I am on the Payees page
    When I select both payees using checkboxes
    And I click "Merge"
    And I choose "ORLEN SA" as the payee to keep
    And I confirm the merge
    Then only "ORLEN SA" remains in the payees list
    And all transactions previously linked to "ORLEN STACJA 401" are now linked to "ORLEN SA"

  KAL-PAY-008 @manual
  Scenario: Merge three payees into one
    Given there are payees "ORLEN SA", "ORLEN STACJA 401", and "ORLEN STACJA 999"
    And all three have linked transactions
    And I am on the Payees page
    When I select all three payees using checkboxes
    And I click "Merge"
    And I choose "ORLEN SA" as the payee to keep
    And I confirm the merge
    Then only "ORLEN SA" remains in the payees list
    And all transactions from the merged payees are linked to "ORLEN SA"

  KAL-PAY-009 @automated
  Scenario: Cannot add a payee without a name
    Given I am on the Payees page
    When I click "Add Payee"
    And I leave "Name" empty
    And I click "Save"
    Then I see a validation error
    And no payee is created

  KAL-PAY-010 @manual
  Scenario: Cannot add two payees with the same name
    Given there is a payee "Biedronka"
    And I am on the Payees page
    When I try to add another payee named "Biedronka"
    Then I see a duplicate name error
    And only one "Biedronka" entry exists in the list
```

## Feature: Payee Identities

The same institution often appears under many spellings in bank exports
("LIDL SP. Z O.O.", "Lidl 1234 Warszawa"). To see who the money really
goes to, similar payees should be detected and merge suggested.

```gherkin
Feature: Payee Identities
  As a user
  I want similar payee names detected and merged
  So that I can see how much I really pay to each institution

  KAL-PID-001 @planned
  Scenario: System suggests merging similarly named payees
    Given payees "LIDL SP. Z O.O." and "Lidl 1234 Warszawa" exist
    When I open the Payees page
    Then I see a merge suggestion grouping the two payees

  KAL-PID-002 @planned
  Scenario: Accepting a merge suggestion rewrites history
    Given a merge suggestion for "LIDL SP. Z O.O." and "Lidl 1234 Warszawa"
    When I accept the suggestion and keep the name "Lidl"
    Then all transactions of both payees point to "Lidl"
    And the duplicate payees are gone

  KAL-PID-003 @planned
  Scenario: Top payees report
    Given transactions across several payees exist
    When I open the "Top payees" report
    Then I see payees ranked by total amount spent in the selected period
```

---

# Workflow 2 — Capture transactions

Daily, weekly, or monthly — whichever cadence the user keeps, entering data must be fast by hand and reliable by import.

## Feature: Manual Transaction Entry

```gherkin
Feature: Manual Transaction Entry
  As a user
  I want to add transactions manually
  So that I can record cash purchases and other off-bank activity

  KAL-TXN-001 @automated
  Scenario: Add an expense transaction
    Given there is an account "PKO Main"
    And there is an expense category "Food"
    And I am on the Transactions page
    When I press Ctrl+N
    And I select type "Expense"
    And I fill in "Amount" with "45.50"
    And I fill in "Description" with "Supermarket"
    And I select category "Food"
    And I click "Save"
    Then I see a transaction for "45.50" with description "Supermarket" in the list

  KAL-TXN-002 @manual
  Scenario: Add an income transaction
    Given there is an account "PKO Main"
    And there is an income category "Salary"
    And I am on the Transactions page
    When I press Ctrl+N
    And I select type "Income"
    And I fill in "Amount" with "5000.00"
    And I select category "Salary"
    And I click "Save"
    Then I see a transaction for "+5,000.00" in the list

  KAL-TXN-003 @manual
  Scenario: Add a transfer between two accounts
    Given there is an account "PKO Main"
    And there is an account "mBank Savings"
    And I am on the Transactions page
    When I press Ctrl+N
    And I select type "Transfer"
    And I fill in "Amount" with "1000.00"
    And I select source account "PKO Main"
    And I select destination account "mBank Savings"
    And I click "Save"
    Then I see a transfer transaction for "1,000.00" in the list

  KAL-TXN-004 @manual
  Scenario: Transaction requires an amount
    Given there is an account "PKO Main"
    And I am on the Transactions page
    When I press Ctrl+N
    And I leave "Amount" empty
    And I click "Save"
    Then I see a validation error
    And no transaction is created

  KAL-TXN-005 @automated
  Scenario: Filter transactions by account
    Given there are transactions on accounts "PKO Main" and "mBank Savings"
    And I am on the Transactions page
    When I filter by account "PKO Main"
    Then I only see transactions for "PKO Main"
```

## Feature: Quick Entry

Consistency is the hard part of tracking finances. Whether entries are
made daily, weekly, or monthly, entering a batch of transactions by hand
must be possible without touching the mouse.

```gherkin
Feature: Quick Entry
  As a user
  I want a keyboard-first, low-friction entry flow
  So that entering transactions regularly does not wear me down

  KAL-QIK-001 @planned
  Scenario: Add an expense using the keyboard only
    Given I am on the Transactions page
    When I press the "new transaction" shortcut
    And I fill the form navigating fields with Tab
    And I press Enter to save
    Then the transaction is saved without any mouse interaction

  KAL-QIK-002 @planned
  Scenario: Quick entry remembers the previous context
    Given I have just saved a transaction for account "mBank" dated 2026-07-05
    When the entry form reopens
    Then "mBank" and 2026-07-05 are preselected

  KAL-QIK-003 @planned
  Scenario: Batch entry keeps the form open
    Given I am entering my weekly backlog of receipts
    When I save a transaction with "save and add next"
    Then the form clears amount and payee but stays open
    And the account and date persist for the next entry
```

## Feature: Transaction Splits

A single receipt ("Lidl 214,50 zł") often spans categories the user
tracks separately (groceries vs alcohol). Splitting must be fast.

```gherkin
Feature: Transaction Splits
  As a user
  I want to split a transaction across categories
  So that I can track things like alcohol separately from groceries

  KAL-SPL-001 @planned
  Scenario: Split an expense into two categories
    Given an expense of 214.50 at payee "Lidl" categorised "Groceries"
    When I split it into 180.00 "Groceries" and 34.50 "Alcohol"
    And I save the split
    Then the transaction shows two split lines
    And the transaction total is still 214.50

  KAL-SPL-002 @planned
  Scenario: Split lines must sum to the original amount
    Given I am splitting an expense of 214.50
    When the split lines sum to 200.00
    Then I see the remaining 14.50 highlighted
    And I cannot save until the lines sum to 214.50

  KAL-SPL-003 @planned
  Scenario: Split lines feed category reports
    Given a saved split of 180.00 "Groceries" and 34.50 "Alcohol"
    When I open spending by category for the month
    Then "Alcohol" includes 34.50 from the split
    And "Groceries" includes 180.00 from the split

  KAL-SPL-004 @planned
  Scenario: Edit an existing split
    Given a transaction with a saved split
    When I change a split line amount and rebalance
    And I save
    Then the updated split lines are stored
```

## Feature: Pagination and Grouping

```gherkin
Feature: Transaction Pagination and Grouping
  As a user
  I want to control how many transactions I see and group them by time
  So that I can navigate large datasets efficiently

  KAL-PAG-001 @manual
  Scenario: Change page size
    Given there are 60 transactions in the database
    And I am on the Transactions page
    When I select "25" in the page size selector
    Then I see exactly 25 transaction rows
    And the pagination shows "Page 1 / 3"

  KAL-PAG-002 @manual
  Scenario: Group transactions by month
    Given there are transactions from different months
    And I am on the Transactions page
    When I select "Month" in the grouping toggle
    Then I see month separator rows between groups of transactions

  KAL-PAG-003 @manual
  Scenario: Group transactions by week
    Given there are transactions from different weeks
    And I am on the Transactions page
    When I select "Week" in the grouping toggle
    Then I see week separator rows (e.g. "W12 2025") between groups

  KAL-PAG-004 @manual
  Scenario: Navigate to next page
    Given there are 60 transactions
    And I am on the Transactions page with page size 25
    When I click the next page button
    Then I see the next 25 transactions
    And the pagination shows "Page 2 / 3"
```

## Feature: mBank CSV Import

```gherkin
Feature: mBank CSV Import
  As a user
  I want to import transactions from an mBank CSV export
  So that I do not have to enter them manually

  KAL-CSV-001 @automated
  Scenario: Successful import of an mBank file
    Given there is an account "mBank PLN"
    And there is an expense category "Other Expenses"
    And there is an income category "Other Income"
    And I am on the Import page
    When I select profile "mBank"
    And I select account "mBank PLN"
    And I select default expense category "Other Expenses"
    And I select default income category "Other Income"
    And I upload a valid mBank CSV file
    Then I see a preview with parsed transactions
    When I click "Import"
    Then I see a success message with the count of imported transactions
    And the transactions appear on the Transactions page

  KAL-CSV-002 @manual
  Scenario: Duplicate transactions are skipped when the option is checked
    Given I have already imported an mBank CSV file
    And I am on the Import page
    And "Skip duplicates" is checked
    When I upload the same mBank CSV file again
    And I click "Import"
    Then I see a message showing 0 new and N skipped transactions

  KAL-CSV-003 @manual
  Scenario: Import blocked when file currency differs from account currency
    Given there is a PLN account "mBank PLN"
    And I am on the Import page
    When I select account "mBank PLN"
    And I upload an mBank CSV file denominated in EUR
    And I click "Import"
    Then I see an error message about currency mismatch
    And no transactions are imported

  KAL-CSV-004 @automated
  Scenario: Transfers to registered accounts are detected automatically
    Given there is an account "mBank PLN" with external number "55114020040000330278886836"
    And there is an account "mBank Savings" with external number "12114020040000330299991234"
    And I import an mBank file for "mBank PLN" that contains a transfer to "12114020040000330299991234"
    Then that transaction is imported as type "Transfer"
    And the other transactions are imported as "Expense" or "Income"
```

## Feature: Transfer Recognition

Bank CSV exports are bookkeeping-style: a transfer between own accounts
shows up as an expense on one side and income on the other, corrupting
totals. Transfers must be recognisable — automatically where possible,
manually otherwise.

```gherkin
Feature: Transfer Recognition
  As a user
  I want transfers between my own accounts recognised as transfers
  So that they do not inflate my income and expense totals

  KAL-TRF-001 @planned
  Scenario: Manually pair two imported rows as a transfer
    Given an imported expense of 500.00 on "mBank" dated 2026-07-01
    And an imported income of 500.00 on "PKO BP" dated 2026-07-01
    When I select both and choose "Mark as transfer"
    Then the two rows become one transfer between "mBank" and "PKO BP"

  KAL-TRF-002 @planned
  Scenario: Import suggests transfer pairs across accounts
    Given imports on two accounts contain matching amounts within 2 days
    When I review the import
    Then the matching rows are suggested as transfer pairs
    And I can accept or dismiss each suggestion

  KAL-TRF-003 @planned
  Scenario: Recognised transfers are excluded from totals
    Given a recognised transfer of 500.00 between my accounts
    When I open the monthly summary
    Then income and expense totals exclude the 500.00
    And the transfer is listed with neutral colouring
```

## Feature: Auto-categorisation Rules

Recurring merchants should not need recurring clicks: a purchase in
Lidl is groceries by default.

```gherkin
Feature: Auto-categorisation Rules
  As a user
  I want rules and suggestions that categorise transactions for me
  So that repeated merchants stop costing me manual work

  KAL-RUL-001 @planned
  Scenario: Create a categorisation rule
    Given I am on the Rules page
    When I add a rule: description contains "LIDL" sets category "Groceries"
    Then the rule appears in the rules list

  KAL-RUL-002 @planned
  Scenario: Rules apply during CSV import
    Given a rule mapping "LIDL" to "Groceries"
    When I import a CSV containing a LIDL transaction
    Then the imported transaction is pre-categorised "Groceries"

  KAL-RUL-003 @planned
  Scenario: Suggest a rule from repeated manual categorisation
    Given I have manually set "Groceries" on three "LIDL" transactions
    When I categorise a fourth "LIDL" transaction the same way
    Then Kaleta offers to create the matching rule

  KAL-RUL-004 @planned
  Scenario: Manual category always wins over a rule
    Given a rule mapping "LIDL" to "Groceries"
    And an imported LIDL transaction pre-categorised "Groceries"
    When I change its category to "Alcohol"
    Then the manual category is kept and the rule does not reapply
```

---

# Workflow 3 — Monthly cycle

Close last month, plan the next one against history, and keep recurring commitments visible.

## Feature: Monthly Readiness

```gherkin
Feature: Monthly Readiness
  As a user
  I want a quick checklist at the turn of the month
  So that I close the previous month and set the next one up for success

  KAL-RDY-001 @manual
  Scenario: Open Monthly Readiness from the Financial Wizard
    Given I completed initial setup
    And I am on the Financial Wizard page
    When I click "Open" on the "Next month check" step
    Then I land on the Monthly Readiness page
    And I see four stages — Close last month, Confirm income, Allocate this month, Acknowledge upcoming bills

  KAL-RDY-002 @manual
  Scenario: Stage 1 — Close last month with no uncategorised transactions
    Given every transaction in last month has a category
    And I am on the Monthly Readiness page
    Then stage 1 shows "0 transactions still need a category"
    When I click "Mark closed" on stage 1
    Then stage 1 is marked as done

  KAL-RDY-003 @manual
  Scenario: Stage 1 — Close last month flags uncategorised transactions
    Given there are 3 uncategorised expense transactions in last month
    And I am on the Monthly Readiness page
    Then stage 1 shows "3 transactions still need a category"
    And I can click "Review transactions" to jump to the Transactions page

  KAL-RDY-004 @manual
  Scenario: Stage 2 — Confirm income compares expected vs actual
    Given there is an active monthly income planned transaction "Salary" of 5000
    And an actual income transaction of 5000 has landed this month
    And I am on the Monthly Readiness page
    Then stage 2 lists "Salary" with expected 5000 and actual 5000
    When I click "Confirm income" on stage 2
    Then stage 2 is marked as done

  KAL-RDY-005 @manual
  Scenario: Stage 3 — Allocate this month copies budgets forward
    Given the previous month has budgets set for categories "Food" and "Rent"
    And the current month has a budget set for "Food" but not "Rent"
    And I am on the Monthly Readiness page
    Then stage 3 shows "1 new, 1 already set"
    When I click "Copy budgets forward"
    Then the current month has budgets for both "Food" and "Rent"
    And the existing "Food" budget is preserved

  KAL-RDY-006 @manual
  Scenario: Stage 4 — Acknowledge upcoming bills
    Given there is an active monthly expense "Rent" of 2000 due this month
    And I am on the Monthly Readiness page
    Then stage 4 lists "Rent" as an unchecked upcoming bill
    When I check the "Rent" checkbox
    Then the "seen" state persists across page reloads

  KAL-RDY-007 @manual
  Scenario: All four stages complete marks the month ready
    Given I have completed stages 1, 2, 3, and 4
    And I am on the Monthly Readiness page
    Then I see "You're ready for the month"
    And the header badge reads "4 / 4 stages done"
```

## Feature: Annual Budget Planning

```gherkin
Feature: Annual Budget Planning
  As a user
  I want to plan monthly spending targets for each category across the full year
  So that I have fine-grained control over my budget and can track execution

  # --- Setting up budgets ---

  KAL-BUD-001 @automated
  Scenario: Set a monthly budget for a single category
    Given there is an expense category "Food"
    And I am on the Budget Plan page for the current year
    When I click the cell for "Food" in the current month column
    And I enter "800"
    And I confirm the entry
    Then the cell shows "800" PLN for "Food" in that month

  KAL-BUD-002 @automated
  Scenario: Set the same amount for all 12 months at once
    Given there is an expense category "Transport"
    And I am on the Budget Plan page
    When I click "Set uniform amount" for "Transport"
    And I enter "300"
    And I confirm
    Then all 12 month columns for "Transport" show "300"
    And the annual total for "Transport" shows "3600"

  KAL-BUD-003 @manual
  Scenario: Set different amounts for each month manually
    Given there is an expense category "Holidays"
    And I am on the Budget Plan page
    When I set "Holidays" budget: Jan=0, Feb=0, Jul=3000, Aug=2000, Dec=1000
    And I leave all other months as 0
    Then the annual total for "Holidays" shows "6000"

  KAL-BUD-004 @manual
  Scenario: Copy previous month budget to current month
    Given there is an expense category "Food" with a budget set in January
    And I am on the Budget Plan page showing February
    When I click "Copy from previous month" for February
    Then all categories in February show the same values as January

  KAL-BUD-005 @automated
  Scenario: Budget totals update when a cell is changed
    Given "Food" has a monthly budget of "800" for all months
    And I am on the Budget Plan page
    When I change "Food" budget for July to "1200"
    Then the annual total for "Food" updates to reflect the change

  # --- Viewing execution ---

  KAL-BUD-006 @automated
  Scenario: See actual spending vs budget for the current month
    Given there are transactions in the current month
    And budget targets are set for the current month
    And I am on the Budget Plan page
    When I select view mode "Budget vs Actual"
    Then each category cell shows both the budgeted amount and the amount actually spent
    And over-budget categories are highlighted in red
    And under-budget categories are highlighted in green

  KAL-BUD-007 @manual
  Scenario: View execution percentage per category
    Given there are budgets and transactions for the current month
    And I am on the Budget Plan page in "Budget vs Actual" mode
    Then each category shows an execution percentage (spent / budgeted × 100)

  # --- Navigating years and months ---

  KAL-BUD-008 @manual
  Scenario: Navigate to a previous year
    Given I am on the Budget Plan page showing the current year
    When I click the previous year button
    Then the page shows the budget grid for the previous year
    And the year label updates accordingly

  KAL-BUD-009 @manual
  Scenario: Navigate to a future year to plan ahead
    Given I am on the Budget Plan page
    When I click the next year button
    Then the page shows an empty or pre-filled grid for next year
    And I can enter budgets for each month

  KAL-BUD-010 @automated
  Scenario: Compare current year to previous year
    Given there are budgets set for both the current year and the previous year
    And I am on the Budget Plan page for the current year
    When I enable "Show previous year"
    Then each cell shows the current year budget and the previous year budget side by side
    And the difference (positive or negative) is displayed

  # --- Validation ---

  KAL-BUD-011 @manual
  Scenario: Cannot enter a negative budget amount
    Given I am on the Budget Plan page
    When I enter "-100" in a budget cell
    Then I see a validation error
    And the cell reverts to its previous value
```

## Feature: Budget Planning Comparisons

Planning next month should lean on evidence: last month's actuals and
the same month in previous years.

```gherkin
Feature: Budget Planning Comparisons
  As a user
  I want to see history while planning next month's category budgets
  So that my plan is grounded in what actually happens

  KAL-CMP-001 @planned
  Scenario: Planning view shows previous month actuals side by side
    Given transactions exist for the previous month
    When I plan next month's budget per category
    Then each category row shows previous month's actual spending

  KAL-CMP-002 @planned
  Scenario: Planning view shows the same month in previous years
    Given budgets and transactions exist for July 2024 and July 2025
    When I plan July 2026
    Then I can see July 2024 and July 2025 actuals per category

  KAL-CMP-003 @planned
  Scenario: Start from last month's plan and adjust
    Given last month has a saved budget plan
    When I choose "copy previous month" while planning
    And I adjust two category amounts
    Then the new plan is saved with my adjustments
```

## Feature: Planned and Recurring Transactions

```gherkin
Feature: Planned and Recurring Transactions
  As a user
  I want to set up recurring transactions for predictable income and expenses
  So that I can automate expected cash flows and use them in forecasting

  # --- Creating planned transactions ---

  KAL-PLN-001 @automated
  Scenario: Create a monthly recurring expense
    Given there is an account "PKO Main"
    And there is an expense category "Subscriptions"
    And I am on the Planned Transactions page
    When I click "Add Planned Transaction"
    And I select type "Expense"
    And I fill in "Name" with "Netflix"
    And I fill in "Amount" with "49"
    And I select account "PKO Main"
    And I select category "Subscriptions"
    And I select frequency "Monthly"
    And I set start date to the 1st of next month
    And I click "Save"
    Then I see "Netflix" in the planned transactions list
    And it is marked as recurring monthly

  KAL-PLN-002 @automated
  Scenario: Create a weekly recurring expense
    Given there is an account "PKO Main"
    And there is an expense category "Food"
    And I am on the Planned Transactions page
    When I click "Add Planned Transaction"
    And I fill in "Name" with "Weekly groceries"
    And I fill in "Amount" with "300"
    And I select account "PKO Main"
    And I select frequency "Weekly"
    And I click "Save"
    Then I see "Weekly groceries" recurring weekly in the planned transactions list

  KAL-PLN-003 @automated
  Scenario: Create a yearly recurring expense
    Given there is an account "PKO Main"
    And there is an expense category "Insurance"
    And I am on the Planned Transactions page
    When I click "Add Planned Transaction"
    And I fill in "Name" with "Car insurance"
    And I fill in "Amount" with "2400"
    And I select account "PKO Main"
    And I select frequency "Yearly"
    And I click "Save"
    Then I see "Car insurance" recurring yearly in the planned transactions list

  KAL-PLN-004 @manual
  Scenario: Create a monthly income with fixed number of occurrences
    Given there is an account "PKO Main"
    And there is an income category "Salary"
    And I am on the Planned Transactions page
    When I click "Add Planned Transaction"
    And I select type "Income"
    And I fill in "Name" with "Freelance contract"
    And I fill in "Amount" with "3000"
    And I select account "PKO Main"
    And I select frequency "Monthly"
    And I set "Occurrences" to "6"
    And I click "Save"
    Then I see "Freelance contract" in the planned transactions list
    And it shows "6 remaining occurrences"

  KAL-PLN-005 @automated
  Scenario: Create a recurring transaction with an end date
    Given there is an account "PKO Main"
    And I am on the Planned Transactions page
    When I click "Add Planned Transaction"
    And I fill in "Name" with "Gym membership"
    And I fill in "Amount" with "120"
    And I select account "PKO Main"
    And I select frequency "Monthly"
    And I set end date to "2025-12-31"
    And I click "Save"
    Then I see "Gym membership" in the planned transactions list
    And it shows end date "2025-12-31"

  KAL-PLN-006 @manual
  Scenario: Create a recurring transfer between accounts
    Given there is an account "PKO Main"
    And there is an account "mBank Savings"
    And I am on the Planned Transactions page
    When I click "Add Planned Transaction"
    And I select type "Transfer"
    And I fill in "Name" with "Monthly savings transfer"
    And I fill in "Amount" with "500"
    And I select source account "PKO Main"
    And I select destination account "mBank Savings"
    And I select frequency "Monthly"
    And I click "Save"
    Then I see "Monthly savings transfer" in the planned transactions list
    And it shows source "PKO Main" and destination "mBank Savings"

  # --- Managing planned transactions ---

  KAL-PLN-007 @automated
  Scenario: Toggle a planned transaction inactive
    Given there is an active planned transaction "Netflix"
    And I am on the Planned Transactions page
    When I click the toggle button for "Netflix"
    Then "Netflix" is marked as inactive
    And it no longer contributes to the forecast

  KAL-PLN-008 @automated
  Scenario: Re-activate a paused planned transaction
    Given there is an inactive planned transaction "Netflix"
    And I am on the Planned Transactions page
    When I click the toggle button for "Netflix"
    Then "Netflix" is marked as active again

  KAL-PLN-009 @automated
  Scenario: Edit a planned transaction amount
    Given there is an active planned transaction "Netflix" with amount 49
    And I am on the Planned Transactions page
    When I click the edit button for "Netflix"
    And I change "Amount" to "59"
    And I click "Save"
    Then "Netflix" shows amount "59" in the planned transactions list

  KAL-PLN-010 @automated
  Scenario: Delete a planned transaction
    Given there is a planned transaction "Old subscription"
    And I am on the Planned Transactions page
    When I click the delete button for "Old subscription"
    And I confirm deletion
    Then "Old subscription" is no longer in the planned transactions list

  # --- Visibility in transactions ---

  KAL-PLN-011 @manual
  Scenario: Planned transactions appear as upcoming in the Transactions page
    Given there is an active planned monthly transaction "Netflix" starting next month
    And I am on the Transactions page
    When I enable the "Show planned" toggle
    Then I see "Netflix" displayed as an upcoming transaction for next month
    And it is visually distinct from recorded transactions

  KAL-PLN-012 @automated
  Scenario: Planned transaction does not appear in transactions without the toggle
    Given there is an active planned transaction "Netflix"
    And I am on the Transactions page
    When the "Show planned" toggle is off
    Then I do not see "Netflix" in the transactions list

  # --- Forecast integration ---

  KAL-PLN-013 @manual
  Scenario: Planned transactions are included in forecast when toggled on
    Given there is an account "PKO Main"
    And there is an active planned monthly income "Salary" of 5000
    And I am on the Forecast page
    When I select account "PKO Main"
    And I enable "Include planned transactions"
    And I click "Run forecast"
    Then the forecast chart shows expected monthly salary inflows

  KAL-PLN-014 @manual
  Scenario: Forecast without planned transactions ignores them
    Given there is an active planned monthly income "Salary" of 5000
    And I am on the Forecast page
    When I disable "Include planned transactions"
    And I click "Run forecast"
    Then the forecast is based solely on historical transaction patterns
```

## Feature: Recurring Payment Detection

Planned transactions exist, but wiring real history to them is tedious.
Payments that repeat with a stable amount and cadence should be
detected and turned into planned transactions in one step — this also
feeds the forecast.

```gherkin
Feature: Recurring Payment Detection
  As a user
  I want repeated payments detected and convertible to planned transactions
  So that my forecast reflects reality without manual bookkeeping

  KAL-REC-001 @planned
  Scenario: Detect a stable monthly payment
    Given three consecutive months contain a 49.99 payment to "Netflix"
    When I open the Recurring suggestions panel
    Then "Netflix 49.99 monthly" is listed as a detected recurring payment

  KAL-REC-002 @planned
  Scenario: Convert a detection to a planned transaction
    Given a detected recurring payment "Netflix 49.99 monthly"
    When I click "Create planned transaction" on it
    Then a monthly planned transaction for 49.99 to "Netflix" exists
    And the detection is marked as handled

  KAL-REC-003 @planned
  Scenario: Link past transactions to the planned series
    Given a planned transaction created from a detection
    When I view the planned transaction
    Then the historical payments that produced the detection are linked to it

  KAL-REC-004 @planned
  Scenario: Amount drift is flagged
    Given a planned transaction "Netflix 49.99 monthly"
    When a new matching payment arrives at 54.99
    Then Kaleta flags the price change and offers to update the plan
```

## Feature: Subscriptions Panel

One place listing every subscription — what, how much, monthly or
yearly — instead of reconstructing it from memory.

```gherkin
Feature: Subscriptions Panel
  As a user
  I want a single panel of all my subscriptions
  So that I know what I pay for, how often, and what it sums to

  KAL-SUB-001 @planned
  Scenario: Subscriptions are listed with cadence and price
    Given subscriptions "Netflix 49.99 monthly" and "Domain 120.00 yearly" exist
    When I open the Subscriptions panel
    Then I see both with their price and billing cadence

  KAL-SUB-002 @planned
  Scenario: Panel shows the normalised monthly total
    Given subscriptions "Netflix 49.99 monthly" and "Domain 120.00 yearly"
    When I open the Subscriptions panel
    Then the total shows 59.99 per month (120.00 / 12 = 10.00 included)

  KAL-SUB-003 @planned
  Scenario: Add a subscription from a detected recurring payment
    Given a detected recurring payment "Spotify 23.99 monthly"
    When I choose "Track as subscription" on it
    Then "Spotify" appears in the Subscriptions panel

  KAL-SUB-004 @planned
  Scenario: Mark a subscription as cancelled
    Given subscription "Netflix 49.99 monthly" is tracked
    When I mark it cancelled as of end of this month
    Then it moves to the cancelled section
    And it no longer counts toward the monthly total
```

---

# Workflow 4 — Annual cycle

Once a year: review, fund the irregular expenses, plan the gifts.

## Feature: Annual Review

Once a year the whole setup deserves a look: category budgets for the
new year, subscriptions worth keeping, irregular items to fund.

```gherkin
Feature: Annual Review
  As a user
  I want a guided yearly review
  So that I plan the coming year in one sitting

  KAL-ANR-001 @planned
  Scenario: Annual review summarises the closing year
    Given a year of transactions and budgets exists
    When I start the Annual Review
    Then I see per-category totals of plan vs actual for the year

  KAL-ANR-002 @planned
  Scenario: Carry budgets into the next year with adjustments
    Given the Annual Review shows this year's category budgets
    When I carry them into next year and raise "Insurance" by 10%
    Then next year's budget plan is created with the adjustment

  KAL-ANR-003 @planned
  Scenario: Review subscriptions and irregular items
    Given tracked subscriptions and irregular fund items exist
    When I reach the review's commitments step
    Then each subscription and irregular item asks for keep / adjust / drop
```

## Feature: Irregular Expenses Fund

Yearly and surprise costs (car insurance, property tax, a heating
underpayment) are paid from a dedicated fund. Each yearly item's cost is
divided by 10 — not 12 — because it is always more expensive than last
time, and the surplus also covers rises and contingencies.

```gherkin
Feature: Irregular Expenses Fund
  As a user
  I want a fund fed monthly that covers irregular yearly costs
  So that an insurance bill or tax never surprises my monthly budget

  KAL-IRR-001 @planned
  Scenario: Define an irregular yearly item
    Given I am on the Irregular Fund page
    When I add item "Car insurance" with yearly amount 1200.00
    Then the item appears with a monthly contribution of 120.00 (1200 / 10)

  KAL-IRR-002 @planned
  Scenario: Fund shows the total monthly contribution
    Given items "Car insurance 1200.00" and "Property tax 600.00" exist
    When I open the Irregular Fund page
    Then the required monthly contribution shows 180.00

  KAL-IRR-003 @planned
  Scenario: Monthly contribution is a planned transfer
    Given the fund's monthly contribution is 180.00
    When I accept the suggested funding plan
    Then a monthly planned transfer of 180.00 to the fund account exists

  KAL-IRR-004 @planned
  Scenario: Pay an item from the fund
    Given the fund holds 1500.00 and item "Car insurance" is due
    When I record the 1250.00 insurance payment from the fund account
    Then the payment is linked to the "Car insurance" item
    And the fund balance shows 250.00

  KAL-IRR-005 @planned
  Scenario: Unplanned expense covered by the fund
    Given the fund holds 800.00
    When I record a 300.00 "heating underpayment" from the fund
    Then the expense is marked as unplanned within the fund history
    And the fund balance shows 500.00
```

## Feature: Gift Planning

A list of people and occasions with planned amounts; the yearly total
feeds the Irregular Expenses Fund, so Christmas never raids December's
budget.

```gherkin
Feature: Gift Planning
  As a user
  I want to plan gifts per person and occasion for the year
  So that gift money is saved up ahead of time

  KAL-GFT-001 @planned
  Scenario: Maintain the gift list
    Given I am on the Gifts page
    When I add "Mum — birthday — 200.00" and "Mum — Christmas — 150.00"
    Then both entries appear grouped under "Mum"
    And the yearly gifts total shows 350.00

  KAL-GFT-002 @planned
  Scenario: Gift total feeds the irregular fund
    Given the yearly gifts total is 350.00
    When I open the Irregular Fund page
    Then a "Gifts" item with yearly amount 350.00 is included

  KAL-GFT-003 @planned
  Scenario: Mark a gift as bought
    Given gift "Mum — birthday — 200.00" is planned
    When I link a 189.99 transaction to that gift
    Then the gift is marked bought with its actual cost
```

---

# Workflow 5 — Funds and goals

The second budgeting dimension besides categories: money set aside on purpose.

## Feature: Savings Goals (Skarbonki)

The second kind of budget besides categories: money set aside toward a
concrete goal — holidays, a new laptop.

```gherkin
Feature: Savings Goals (Skarbonki)
  As a user
  I want piggy-bank style goals with targets and progress
  So that saving for holidays is visible and deliberate

  KAL-GOL-001 @planned
  Scenario: Create a savings goal
    Given I am on the Goals page
    When I add goal "Holidays 2027" with target 6000.00 by 2027-06-01
    Then the goal appears with 0% progress

  KAL-GOL-002 @planned
  Scenario: Contribute to a goal
    Given goal "Holidays 2027" with target 6000.00
    When I record a 500.00 contribution to it
    Then the goal shows 500.00 saved and 8% progress

  KAL-GOL-003 @planned
  Scenario: Pace hint against the target date
    Given goal "Holidays 2027" is 500.00 of 6000.00 with 11 months left
    When I view the goal
    Then I see the required monthly pace of 500.00 to reach the target

  KAL-GOL-004 @planned
  Scenario: Close a goal and release the money
    Given goal "Holidays 2027" has reached its target
    When I close the goal
    Then its balance is released back to the source account
    And the goal moves to the archive
```

## Feature: Reserve Funds

Two non-negotiable safety nets: emergency cash at home (2–5k zł) and a
security fund covering at least 3 months of living costs.

```gherkin
Feature: Reserve Funds
  As a user
  I want my emergency cash and security fund tracked against targets
  So that I always know whether my safety nets are intact

  KAL-FND-001 @planned
  Scenario: Track emergency cash at home
    Given a cash account "Emergency cash" marked as a reserve with target 3000.00
    When I open the Reserves panel
    Then I see its balance against the 3000.00 target

  KAL-FND-002 @planned
  Scenario: Security fund target derives from real spending
    Given my average monthly expenses over the last 12 months are 5200.00
    And an account "Security fund" is marked as a 3-month reserve
    When I open the Reserves panel
    Then its target shows 15600.00

  KAL-FND-003 @planned
  Scenario: Warning when a reserve falls below target
    Given "Emergency cash" holds 1800.00 against a 3000.00 target
    When I open the dashboard
    Then I see a warning that the reserve is below target
```

---

# Workflow 6 — Insight

Why the data is collected at all: seeing where the money stands and where it is heading.

## Feature: Account Balance Forecast

```gherkin
Feature: Account Balance Forecast
  As a user
  I want to forecast future account balances based on history and planned transactions
  So that I can anticipate shortfalls or surpluses and plan ahead

  # --- Single-account forecast ---

  KAL-FCT-001 @automated
  Scenario: Run a 30-day forecast for a single account
    Given there is an account "PKO Main" with at least 90 days of transaction history
    And I am on the Forecast page
    When I select account "PKO Main"
    And I set horizon to "30 days"
    And I click "Run forecast"
    Then I see a chart with historical balance and a predicted balance line
    And the predicted balance for day 30 is displayed
    And a shaded confidence interval surrounds the prediction

  KAL-FCT-002 @automated
  Scenario: Run a 90-day forecast for a single account
    Given there is an account "PKO Main" with sufficient history
    And I am on the Forecast page
    When I select account "PKO Main"
    And I set horizon to "90 days"
    And I click "Run forecast"
    Then the forecast chart extends 90 days beyond today

  # --- Multi-account forecast ---

  KAL-FCT-003 @automated
  Scenario: Run a forecast for all accounts combined
    Given there are accounts "PKO Main", "mBank Savings", and "Cash"
    And I am on the Forecast page
    When I select "All accounts"
    And I set horizon to "30 days"
    And I click "Run forecast"
    Then the forecast chart shows the combined balance of all three accounts
    And individual account lines are shown as secondary series

  KAL-FCT-004 @manual
  Scenario: Run a forecast for a selected subset of accounts
    Given there are accounts "PKO Main", "mBank Savings", and "Cash"
    And I am on the Forecast page
    When I select accounts "PKO Main" and "mBank Savings"
    And I click "Run forecast"
    Then the forecast shows the combined balance of the two selected accounts only

  # --- Planned transaction toggle ---

  KAL-FCT-005 @manual
  Scenario: Forecast includes planned transactions when toggled on
    Given there is an account "PKO Main" with history
    And there is an active planned monthly expense "Rent" of 2000
    And I am on the Forecast page
    When I select account "PKO Main"
    And I enable "Include planned transactions"
    And I click "Run forecast"
    Then monthly rent deductions are visible as markers on the forecast chart
    And the predicted balance reflects the recurring expense

  KAL-FCT-006 @manual
  Scenario: Forecast ignores planned transactions when toggled off
    Given there is an account "PKO Main" with history
    And there is an active planned monthly expense "Rent" of 2000
    And I am on the Forecast page
    When I select account "PKO Main"
    And I disable "Include planned transactions"
    And I click "Run forecast"
    Then rent deductions are not marked on the chart
    And the prediction is based on historical patterns only

  # --- Edge cases ---

  KAL-FCT-007 @automated
  Scenario: Warning shown when history is insufficient
    Given there is an account "New Account" with only 7 days of transactions
    And I am on the Forecast page
    When I select account "New Account"
    And I click "Run forecast"
    Then I see a warning "Insufficient history for a reliable forecast"
    And no chart is displayed

  KAL-FCT-008 @manual
  Scenario: Forecast shows balance reaching zero alert
    Given there is an account "PKO Main" with a low balance and regular expenses
    And I am on the Forecast page
    When I run the forecast
    And the predicted balance crosses zero within the forecast horizon
    Then the chart highlights the date the balance is predicted to reach zero
    And I see a warning "Balance may reach zero on [date]"

  KAL-FCT-009 @manual
  Scenario: Fallback projection when Prophet is not installed
    Given Kaleta is installed without the optional forecast extra
    And I am on the Forecast page
    Then I see a banner "Advanced forecasting (Prophet) not installed — using simple projection"
    And a link to install instructions is visible
    And the Prophet-only preset selector is hidden
    When I click "Run Forecast"
    Then I see a chart with historical balance and a predicted balance line
    And a shaded confidence interval surrounds the prediction
```

## Feature: Credit Calculator

```gherkin
Feature: Credit Calculator
  As a user
  I want to calculate loan repayment schedules for common credit types
  So that I can understand total costs and compare financing options

  # --- Loan types ---

  KAL-CRD-001 @automated
  Scenario: Calculate a standard consumer loan with equal installments
    Given I am on the Credit Calculator page
    When I select loan type "Consumer Loan"
    And I fill in "Loan Amount" with "30000"
    And I fill in "Annual Interest Rate" with "9.5"
    And I fill in "Term" with "36" months
    And I select installment type "Equal"
    And I click "Calculate"
    Then I see the monthly installment amount
    And I see total interest paid
    And I see total repayment amount

  KAL-CRD-002 @automated
  Scenario: Calculate a car loan with equal installments
    Given I am on the Credit Calculator page
    When I select loan type "Car Loan"
    And I fill in "Loan Amount" with "80000"
    And I fill in "Annual Interest Rate" with "7.99"
    And I fill in "Term" with "60" months
    And I select installment type "Equal"
    And I click "Calculate"
    Then I see the monthly installment amount
    And I see the amortization schedule table
    And each row shows payment number, installment, principal, interest, and remaining balance

  KAL-CRD-003 @automated
  Scenario: Calculate a mortgage with equal installments
    Given I am on the Credit Calculator page
    When I select loan type "Mortgage"
    And I fill in "Loan Amount" with "500000"
    And I fill in "Annual Interest Rate" with "6.5"
    And I fill in "Term" with "360" months
    And I select installment type "Equal"
    And I click "Calculate"
    Then I see the monthly installment amount
    And I see total interest paid over 30 years
    And I see the amortization schedule table

  # --- Installment type comparison ---

  KAL-CRD-004 @automated
  Scenario: Compare equal vs decreasing installments
    Given I am on the Credit Calculator page
    When I fill in loan details: amount "100000", rate "8.0", term "120" months
    And I select installment type "Equal"
    And I note the total interest amount
    When I switch to installment type "Decreasing"
    Then the first installment is higher than the equal installment
    And the total interest paid is lower than for equal installments
    And a comparison summary is shown

  # --- Overpayment simulation ---

  KAL-CRD-005 @automated
  Scenario: Simulate overpayment to shorten loan term
    Given I have calculated a mortgage: 500000 PLN, 6.5%, 360 months, equal installments
    When I enter an extra monthly payment of "500" in the overpayment field
    And I click "Recalculate"
    Then I see the new loan term is shorter than 360 months
    And I see how many months are saved
    And I see total interest saved

  KAL-CRD-006 @manual
  Scenario: Simulate a one-off lump-sum overpayment
    Given I have calculated a consumer loan
    When I enter a one-off overpayment of "10000" at month "12"
    And I click "Recalculate"
    Then I see the updated schedule from month 12 onward
    And the remaining balance drops accordingly

  # --- Validation ---

  KAL-CRD-007 @manual
  Scenario: Cannot calculate without required fields
    Given I am on the Credit Calculator page
    When I leave "Loan Amount" empty
    And I click "Calculate"
    Then I see a validation error on "Loan Amount"
    And no result is shown

  KAL-CRD-008 @automated
  Scenario: Interest rate must be positive
    Given I am on the Credit Calculator page
    When I fill in "Annual Interest Rate" with "0"
    And I click "Calculate"
    Then I see a validation error indicating rate must be greater than zero
```

## Feature: Debt Tracking

Money lent to people gets lost in general transactions. A dedicated
panel tracks who owes what, with entries linked to the regular ledger.

```gherkin
Feature: Debt Tracking
  As a user
  I want a panel of personal debts linked to my transactions
  So that lending money does not mean losing track of it

  KAL-DBT-001 @planned
  Scenario: Record money lent to a person
    Given I am on the Debts panel
    When I record lending 400.00 to "Marek" linked to yesterday's transfer
    Then "Marek" shows an outstanding balance of 400.00

  KAL-DBT-002 @planned
  Scenario: Panel shows balance per person
    Given "Marek" owes 400.00 and I owe "Ania" 150.00
    When I open the Debts panel
    Then I see +400.00 for "Marek" and -150.00 for "Ania"

  KAL-DBT-003 @planned
  Scenario: Repayment reduces the balance
    Given "Marek" owes 400.00
    When I link an incoming 250.00 transaction as his repayment
    Then "Marek" shows an outstanding balance of 150.00

  KAL-DBT-004 @planned
  Scenario: Lent money is not an expense
    Given a 400.00 transfer recorded as a loan to "Marek"
    When I open the monthly spending summary
    Then the 400.00 is shown under loans, not regular expenses
```

## Feature: Investment Tracking

Beyond cash: the value of ETFs, stocks, and bonds tracked alongside
accounts for a full net-worth picture.

```gherkin
Feature: Investment Tracking
  As a user
  I want to track investment holdings and their value
  So that my net worth includes more than my bank accounts

  KAL-INV-001 @planned
  Scenario: Add a holding
    Given I am on the Investments page
    When I add 10 units of ETF "V80A" bought at 420.00 each
    Then the holding appears with a cost basis of 4200.00

  KAL-INV-002 @planned
  Scenario: Update the valuation
    Given a holding of 10 units of "V80A"
    When I update the unit price to 450.00
    Then the holding value shows 4500.00 and gain +300.00

  KAL-INV-003 @planned
  Scenario: Investments count toward net worth
    Given accounts total 20000.00 and holdings are valued at 4500.00
    When I view the net worth summary
    Then it shows 24500.00 with an investments breakdown

  KAL-INV-004 @planned
  Scenario: Contribution linked to a transfer
    Given a 1000.00 transfer to my brokerage account
    When I link it to a purchase of "V80A" units
    Then the transfer is categorised as an investment contribution
```

## Feature: AI Insights

Natural-language analysis of the ledger — the commercial layer on top
of the open core (see roadmap: paid tier = AI + hosting).

```gherkin
Feature: AI Insights
  As a user
  I want plain-language summaries and anomaly call-outs
  So that the data tells me things I did not think to ask

  KAL-AIN-001 @planned
  Scenario: Monthly narrative summary
    Given a closed month of transactions and budgets
    When I open the month's AI summary
    Then I see a short narrative covering totals, biggest deviations, and trends

  KAL-AIN-002 @planned
  Scenario: Anomaly is pointed out with context
    Given electricity spending doubled versus its 6-month average
    When the monthly summary is generated
    Then the summary highlights the electricity anomaly with the comparison
```

---

# Workflow 7 — Platform

Cross-cutting guarantees: access control, data safety, automation.

## Feature: Authentication

```gherkin
Feature: Single-user authentication
  As the Kaleta owner
  I want to sign in with a password
  So that only I can access my financial data

  KAL-AUTH-001 @automated
  Scenario: Successful login redirects to the dashboard
    Given a Kaleta user exists with username "e2e" and a known password
    And I am on the login page
    When I enter the correct username and password and submit
    Then I am redirected away from the login page
    And I can see the dashboard

  KAL-AUTH-002 @automated
  Scenario: Wrong password shows a generic error
    Given a Kaleta user exists with username "e2e" and a known password
    And I am on the login page
    When I enter the correct username and a wrong password and submit
    Then I remain on the login page
    And I see a generic invalid-credentials message

  KAL-AUTH-003 @automated
  Scenario: Unauthenticated deep link redirects to login
    Given I am not signed in
    When I open "/transactions" directly
    Then I am redirected to the login page
    And the redirect preserves the originally requested path

  KAL-AUTH-004 @automated
  Scenario: Unauthenticated setup page on a configured install redirects to login
    Given a database is already configured
    And I am not signed in
    When I open "/setup" directly
    Then I am redirected to the login page
    And the redirect preserves the originally requested path

  KAL-AUTH-005 @automated
  Scenario: API returns 401 JSON without a bearer token
    Given I am not signed in
    When I request "/api/v1/accounts/" without credentials
    Then the response status is 401
    And the JSON body reports unauthorized

  KAL-AUTH-006 @automated
  Scenario: API returns 200 with a valid bearer token
    Given a valid API bearer token exists
    When I request "/api/v1/accounts/" with the bearer token
    Then the response status is 200
```

## Feature: Settings — Data safety

```gherkin
Feature: Settings — Data safety
  As a user
  I want destructive data actions to require explicit confirmation
  So that I cannot accidentally wipe or lose my financial records

  KAL-SET-013 @automated
  Scenario: Wipe requires typing DELETE — wrong text keeps the action disabled
    Given I am on the Settings page, Data tab
    When I open the "Clear all data" confirmation dialog
    Then the confirm wipe button is disabled
    When I type "delete" in the confirmation field
    Then the confirm wipe button remains disabled
    And my existing accounts and transactions are unchanged

  KAL-SET-014 @manual
  Scenario: Backup export produces a downloadable file
    Given I have at least one account with transactions
    And I am on the Settings page, Data tab
    When I click "Export backup"
    Then a ZIP file download starts
    And the filename matches the pattern "kaleta_backup_*.zip"

  KAL-SET-015 @manual
  Scenario: Restore from a backup file restores accounts and transactions
    Given I exported a backup containing accounts and transactions
    And I cleared all data from the database
    And I am on the Settings page, Data tab
    When I upload the backup ZIP and confirm restore
    Then my accounts and transactions from the backup are present again
```

## Feature: Public API

Automation is a first-class exit: everything the UI can do should be
scriptable with a bearer token, so users can integrate imports, LLMs,
or home automation.

```gherkin
Feature: Public API
  As a user
  I want a documented REST API covering core resources
  So that I can automate and integrate Kaleta with my own tools

  KAL-API-001 @planned
  Scenario: Create a transaction via the API
    Given a valid API bearer token
    When I POST a transaction to /api/v1/transactions
    Then the response is 201 and the transaction appears in the UI

  KAL-API-002 @planned
  Scenario: Read budgets via the API
    Given a valid API bearer token and budgets for the current month
    When I GET /api/v1/budgets for the current month
    Then the response contains the per-category planned amounts

  KAL-API-003 @planned
  Scenario: API schema is discoverable
    Given a running instance
    When I open the OpenAPI documentation endpoint
    Then all public endpoints are listed with request and response schemas
```

---

## Notes for test implementation

- Tests live in `tests/e2e/`
- Each feature file maps to one test module: `test_<feature>.py`
- Use `pytest-playwright` (sync API via `page` fixture)
- The app must be running on `http://localhost:8080` before the suite starts
- Use a dedicated test database (set `KALETA_DB_URL` env var to a temp SQLite file)
- Fixtures in `tests/e2e/conftest.py` handle: starting the app with a test DB, seeding prerequisite data via the service layer, and cleanup
- Scenario steps translate directly to Playwright actions — no `pytest-bdd` required unless Gherkin step-binding is desired
