# Kaleta — BDD Scenarios (Gherkin)

All scenarios run against a live Kaleta instance at `http://localhost:8080`.
The app must be started before the scenario suite runs.
Each scenario uses a fresh isolated database (see `tests/e2e/conftest.py`).

---

## Feature: Institution Management

```gherkin
Feature: Institution Management
  As a user
  I want to manage financial institutions
  So that I can organise my accounts by the bank or provider they belong to

  Scenario: Add a new institution
    Given I am on the Institutions page
    When I click "Add Institution"
    And I fill in "Name" with "PKO Bank Polski"
    And I select type "Bank"
    And I click "Save"
    Then I see "PKO Bank Polski" in the institutions list

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

  Scenario: Edit an existing institution
    Given there is an institution "PKO Bank Polski"
    And I am on the Institutions page
    When I click the edit button for "PKO Bank Polski"
    And I change "Name" to "PKO BP"
    And I click "Save"
    Then I see "PKO BP" in the institutions list
    And I do not see "PKO Bank Polski"

  Scenario: Delete an institution with no linked accounts
    Given there is an institution "Old Bank" with no accounts
    And I am on the Institutions page
    When I click the delete button for "Old Bank"
    And I confirm deletion
    Then "Old Bank" is no longer in the institutions list

  Scenario: Delete an institution that has linked accounts
    Given there is an institution "PKO BP" with at least one linked account
    And I am on the Institutions page
    When I click the delete button for "PKO BP"
    And I confirm deletion
    Then "PKO BP" is no longer in the institutions list
    And the previously linked accounts still exist without an institution reference

  Scenario: Cannot add an institution without a name
    Given I am on the Institutions page
    When I click "Add Institution"
    And I leave "Name" empty
    And I click "Save"
    Then I see a validation error
    And no institution is created

  Scenario: Cannot add two institutions with the same name
    Given there is an institution "mBank"
    And I am on the Institutions page
    When I try to add another institution named "mBank"
    Then I see a duplicate name error
    And only one "mBank" entry exists in the list

  Scenario: Institution type defaults to Bank
    Given I am on the Institutions page
    When I click "Add Institution"
    Then the "Type" field defaults to "Bank"
```

---

## Feature: Account Management

```gherkin
Feature: Account Management
  As a user
  I want to manage my bank accounts
  So that I can track money across multiple accounts

  Scenario: Add a new account
    Given I am on the Accounts page
    When I click "Add Account"
    And I fill in "Name" with "PKO Main"
    And I fill in "Currency" with "PLN"
    And I click "Save"
    Then I see "PKO Main" in the accounts list

  Scenario: Edit an existing account
    Given there is an account "PKO Main"
    And I am on the Accounts page
    When I click the edit button for "PKO Main"
    And I change "Name" to "PKO Personal"
    And I click "Save"
    Then I see "PKO Personal" in the accounts list
    And I do not see "PKO Main"

  Scenario: Delete an account
    Given there is an account "Old Account"
    And I am on the Accounts page
    When I click the delete button for "Old Account"
    And I confirm deletion
    Then I do not see "Old Account" in the accounts list

  Scenario: Cannot add account without a name
    Given I am on the Accounts page
    When I click "Add Account"
    And I leave "Name" empty
    And I click "Save"
    Then I see a validation error
    And the account is not created
```

---

## Feature: Category Management

```gherkin
Feature: Category Management
  As a user
  I want to organise transactions into categories
  So that I can analyse my spending

  Scenario: Add a root expense category
    Given I am on the Categories page
    When I click "Add Category" in the Expense section
    And I fill in "Name" with "Food"
    And I click "Save"
    Then I see "Food" in the expense categories list

  Scenario: Add a subcategory under an existing parent
    Given there is an expense category "Food"
    And I am on the Categories page
    When I click "Add Category" in the Expense section
    And I fill in "Name" with "Groceries"
    And I select "Food" as the parent
    And I click "Save"
    Then I see "Food → Groceries" in the expense categories list

  Scenario: Edit a category name
    Given there is an expense category "Food"
    And I am on the Categories page
    When I click the edit button for "Food"
    And I change "Name" to "Groceries & Food"
    And I click "Save"
    Then I see "Groceries & Food" in the expense categories list
    And I do not see "Food" as a root category

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

  Scenario: Promote a subcategory to root
    Given there is an expense category "Food"
    And there is a subcategory "Groceries" under "Food"
    And I am on the Categories page
    When I click the edit button for "Food → Groceries"
    And I clear the parent field
    And I click "Save"
    Then I see "Groceries" as a root expense category
    And all transactions previously in "Food → Groceries" remain linked to "Groceries"

  Scenario: Delete a leaf category with no transactions
    Given there is an expense category "Food"
    And there is a subcategory "Snacks" under "Food" with no transactions
    And I am on the Categories page
    When I click the delete button for "Food → Snacks"
    And I confirm deletion
    Then "Snacks" is no longer in the categories list

  Scenario: Delete a category that has transactions
    Given there is an expense category "Food" with linked transactions
    And I am on the Categories page
    When I click the delete button for "Food"
    And I confirm deletion
    Then "Food" is no longer in the categories list
    And the previously linked transactions still exist with no category

  Scenario: Delete a parent category also removes its children
    Given there is an expense category "Food"
    And there is a subcategory "Groceries" under "Food"
    And I am on the Categories page
    When I click the delete button for "Food"
    And I confirm deletion
    Then "Food" is no longer in the categories list
    And "Groceries" is no longer in the categories list

  Scenario: Two subcategories with the same name under different parents
    Given there is an expense category "Food"
    And there is an expense category "Transport"
    And I am on the Categories page
    When I add subcategory "Other" under "Food"
    And I add subcategory "Other" under "Transport"
    Then I see "Food → Other" in the categories list
    And I see "Transport → Other" in the categories list

  Scenario: Cannot add two root categories with the same name
    Given there is an expense category "Food"
    And I am on the Categories page
    When I try to add another expense category named "Food" without a parent
    Then I see a duplicate name error
```

---

## Feature: Manual Transaction Entry

```gherkin
Feature: Manual Transaction Entry
  As a user
  I want to add transactions manually
  So that I can record cash purchases and other off-bank activity

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

  Scenario: Transaction requires an amount
    Given there is an account "PKO Main"
    And I am on the Transactions page
    When I press Ctrl+N
    And I leave "Amount" empty
    And I click "Save"
    Then I see a validation error
    And no transaction is created

  Scenario: Filter transactions by account
    Given there are transactions on accounts "PKO Main" and "mBank Savings"
    And I am on the Transactions page
    When I filter by account "PKO Main"
    Then I only see transactions for "PKO Main"
```

---

## Feature: Pagination and Grouping

```gherkin
Feature: Transaction Pagination and Grouping
  As a user
  I want to control how many transactions I see and group them by time
  So that I can navigate large datasets efficiently

  Scenario: Change page size
    Given there are 60 transactions in the database
    And I am on the Transactions page
    When I select "25" in the page size selector
    Then I see exactly 25 transaction rows
    And the pagination shows "Page 1 / 3"

  Scenario: Group transactions by month
    Given there are transactions from different months
    And I am on the Transactions page
    When I select "Month" in the grouping toggle
    Then I see month separator rows between groups of transactions

  Scenario: Group transactions by week
    Given there are transactions from different weeks
    And I am on the Transactions page
    When I select "Week" in the grouping toggle
    Then I see week separator rows (e.g. "W12 2025") between groups

  Scenario: Navigate to next page
    Given there are 60 transactions
    And I am on the Transactions page with page size 25
    When I click the next page button
    Then I see the next 25 transactions
    And the pagination shows "Page 2 / 3"
```

---

## Feature: mBank CSV Import

```gherkin
Feature: mBank CSV Import
  As a user
  I want to import transactions from an mBank CSV export
  So that I do not have to enter them manually

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

  Scenario: Duplicate transactions are skipped when the option is checked
    Given I have already imported an mBank CSV file
    And I am on the Import page
    And "Skip duplicates" is checked
    When I upload the same mBank CSV file again
    And I click "Import"
    Then I see a message showing 0 new and N skipped transactions

  Scenario: Import blocked when file currency differs from account currency
    Given there is a PLN account "mBank PLN"
    And I am on the Import page
    When I select account "mBank PLN"
    And I upload an mBank CSV file denominated in EUR
    And I click "Import"
    Then I see an error message about currency mismatch
    And no transactions are imported

  Scenario: Transfers to registered accounts are detected automatically
    Given there is an account "mBank PLN" with external number "55114020040000330278886836"
    And there is an account "mBank Savings" with external number "12114020040000330299991234"
    And I import an mBank file for "mBank PLN" that contains a transfer to "12114020040000330299991234"
    Then that transaction is imported as type "Transfer"
    And the other transactions are imported as "Expense" or "Income"
```

---

## Feature: Tag Management

```gherkin
Feature: Tag Management
  As a user
  I want to create, edit, and remove tags
  So that I can label transactions with cross-cutting topics (e.g. "vacation", "business")

  Scenario: Add a tag
    Given I am on the Tags page
    When I click "Add Tag"
    And I fill in "Name" with "Vacation"
    And I pick a colour
    And I click "Save"
    Then I see "Vacation" in the tags list

  Scenario: Add a tag with all optional fields
    Given I am on the Tags page
    When I click "Add Tag"
    And I fill in "Name" with "Business"
    And I fill in "Description" with "Work-related expenses"
    And I fill in "Icon" with "work"
    And I pick a colour
    And I click "Save"
    Then I see "Business" in the tags list with the correct colour and icon

  Scenario: Edit a tag name
    Given there is a tag "Vacation"
    And I am on the Tags page
    When I click the edit button for "Vacation"
    And I change "Name" to "Holiday"
    And I click "Save"
    Then I see "Holiday" in the tags list
    And I do not see "Vacation"

  Scenario: Edit tag colour and description
    Given there is a tag "Business"
    And I am on the Tags page
    When I click the edit button for "Business"
    And I change the colour
    And I change "Description" to "All business travel"
    And I click "Save"
    Then the tag "Business" shows the updated colour and description

  Scenario: Delete a tag
    Given there is a tag "OldTag"
    And I am on the Tags page
    When I click the delete button for "OldTag"
    And I confirm deletion
    Then "OldTag" is no longer in the tags list

  Scenario: Deleting a tag does not delete linked transactions
    Given there is a tag "Vacation"
    And there are transactions tagged with "Vacation"
    And I am on the Tags page
    When I click the delete button for "Vacation"
    And I confirm deletion
    Then "Vacation" is no longer in the tags list
    And the previously tagged transactions still exist without that tag

  Scenario: Cannot add two tags with the same name
    Given there is a tag "Vacation"
    And I am on the Tags page
    When I try to add another tag named "Vacation"
    Then I see a duplicate name error
    And only one "Vacation" entry exists in the list

  Scenario: Cannot add a tag without a name
    Given I am on the Tags page
    When I click "Add Tag"
    And I leave "Name" empty
    And I click "Save"
    Then I see a validation error
    And no tag is created
```

---

## Feature: Payee Management

```gherkin
Feature: Payee Management
  As a user
  I want to manage payees with full contact details and merge duplicates
  So that I can keep my payee list clean and enriched with useful information

  Scenario: Add a payee with name only
    Given I am on the Payees page
    When I click "Add Payee"
    And I fill in "Name" with "Biedronka"
    And I click "Save"
    Then I see "Biedronka" in the payees list

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

  Scenario: Edit a payee name
    Given there is a payee "BIEDRONKA SP Z OO"
    And I am on the Payees page
    When I click the edit button for "BIEDRONKA SP Z OO"
    And I change "Name" to "Biedronka"
    And I click "Save"
    Then I see "Biedronka" in the payees list

  Scenario: Edit payee contact details
    Given there is a payee "Biedronka" with no contact details
    And I am on the Payees page
    When I click the edit button for "Biedronka"
    And I fill in "Address" with "ul. Różana 1"
    And I fill in "City" with "Inowrocław"
    And I fill in "Website" with "https://www.biedronka.pl"
    And I click "Save"
    Then the payee "Biedronka" shows the updated address and website

  Scenario: Delete a payee
    Given there is a payee "OLD PAYEE"
    And I am on the Payees page
    When I click the delete button for "OLD PAYEE"
    And I confirm deletion
    Then "OLD PAYEE" is no longer in the payees list

  Scenario: Deleting a payee does not delete linked transactions
    Given there is a payee "Biedronka" with linked transactions
    And I am on the Payees page
    When I click the delete button for "Biedronka"
    And I confirm deletion
    Then "Biedronka" is no longer in the payees list
    And the previously linked transactions still exist with no payee

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

  Scenario: Cannot add a payee without a name
    Given I am on the Payees page
    When I click "Add Payee"
    And I leave "Name" empty
    And I click "Save"
    Then I see a validation error
    And no payee is created

  Scenario: Cannot add two payees with the same name
    Given there is a payee "Biedronka"
    And I am on the Payees page
    When I try to add another payee named "Biedronka"
    Then I see a duplicate name error
    And only one "Biedronka" entry exists in the list
```

---

## Feature: Onboarding Wizard

```gherkin
Feature: Onboarding Wizard
  As a new user
  I want to be guided through initial setup
  So that I can start tracking finances quickly

  Scenario: Wizard shows incomplete steps for a fresh database
    Given the database is empty
    And I am on the Financial Wizard page
    Then I see the "Na start" onboarding section
    And step "Add an institution" is marked as pending
    And step "Add an account" is marked as pending
    And step "Set up categories" is marked as pending
    And step "Import or add transactions" is marked as pending

  Scenario: Wizard marks steps as done as data is added
    Given I have added an institution and an account
    And I am on the Financial Wizard page
    Then step "Add an institution" is marked as done
    And step "Add an account" is marked as done
    And step "Set up categories" is marked as pending
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
