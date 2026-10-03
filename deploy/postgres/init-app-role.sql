-- SPDX-License-Identifier: AGPL-3.0-or-later
-- The application role of a hosted Kaleta (docs/deployment.md, "Database").
--
-- Not a superuser: it may create schemas in its database (one per account)
-- and the registry tables in `public`, and nothing else. The same statements
-- are run once in the Supabase SQL editor for the hosted instance, with a
-- real password. Run by postgres:16 on first start of compose.hosted-dev.yml.
CREATE ROLE kaleta_app LOGIN PASSWORD 'kaleta_app' NOSUPERUSER NOCREATEDB NOCREATEROLE;
GRANT CONNECT, CREATE ON DATABASE kaleta TO kaleta_app;
GRANT USAGE, CREATE ON SCHEMA public TO kaleta_app;
