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

---

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

---

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
```

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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
```

---

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

---

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

---

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

---

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

---

## Notes for test implementation

- Tests live in `tests/e2e/`
- Each feature file maps to one test module: `test_<feature>.py`
- Use `pytest-playwright` (sync API via `page` fixture)
- The app must be running on `http://localhost:8080` before the suite starts
- Use a dedicated test database (set `KALETA_DB_URL` env var to a temp SQLite file)
- Fixtures in `tests/e2e/conftest.py` handle: starting the app with a test DB, seeding prerequisite data via the service layer, and cleanup
- Scenario steps translate directly to Playwright actions — no `pytest-bdd` required unless Gherkin step-binding is desired
