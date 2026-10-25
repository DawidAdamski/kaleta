# Changelog

## [0.8.1](https://github.com/DawidAdamski/kaleta/compare/v0.8.0...v0.8.1) (2026-10-25)


### Bug Fixes

* **docs:** unbreak Deploy Pages by linking out-of-tree SQL via GitHub URL ([e148209](https://github.com/DawidAdamski/kaleta/commit/e1482092ee38a7d82c3848f97da07f9532949af4))
* **docs:** unbreak Deploy Pages by linking out-of-tree SQL via GitHub URL ([284e891](https://github.com/DawidAdamski/kaleta/commit/284e89195f4a848634bd7ee53edafab4145b9fee))
* **institutions:** store logos in Postgres, not on the pod filesystem ([1080191](https://github.com/DawidAdamski/kaleta/commit/10801915cdbe3e2d73d3f6d5992f0f6863c283d8))
* **institutions:** store logos in Postgres, not on the pod filesystem ([536293a](https://github.com/DawidAdamski/kaleta/commit/536293abb832be276eb3cb1691ee256c09934d65))

## [0.8.0](https://github.com/DawidAdamski/kaleta/compare/v0.7.0...v0.8.0) (2026-10-24)


### Features

* **api:** gate /api-docs behind a flag (F-2) ([c40a18f](https://github.com/DawidAdamski/kaleta/commit/c40a18fef0c580000617bef58cfaa6decdf6d85d))
* **api:** gate /api-docs behind a flag so the schema is not always published ([7a8b012](https://github.com/DawidAdamski/kaleta/commit/7a8b012f9f9c1d06c6fde9c1912a85f284b1d24c))
* **api:** tier /health disclosure so no family reads another's state ([66e5833](https://github.com/DawidAdamski/kaleta/commit/66e583391600f421bd4fe04116384f05d3ce76db))
* **api:** tier /health disclosure so no family reads another's state (F-1) ([68b6378](https://github.com/DawidAdamski/kaleta/commit/68b637800da4f4095497ce8563be3c8acfa013e9))
* **auth:** warn when a production run serves the cookie without Secure ([550d373](https://github.com/DawidAdamski/kaleta/commit/550d373c9350f4338814db3865e5a3bc04e907dd))
* **auth:** warn when a production run serves the cookie without Secure (F-3) ([59378a2](https://github.com/DawidAdamski/kaleta/commit/59378a2986c93f2bfdca34134f0d8ca2efd3fd30))
* **budgets:** unify planning onto the Budgets page as a Plan tab (slice 1) ([a3e534d](https://github.com/DawidAdamski/kaleta/commit/a3e534d0dd078434c2007bb605446c040dc1d291))
* **budgets:** unify planning onto the Budgets page as a Plan tab (slice 1) ([382a3f4](https://github.com/DawidAdamski/kaleta/commit/382a3f409edf817114a94b21a1932d3ef9ce9f14))
* **deploy:** run container images as a non-root user (F-6) ([8e3d6ce](https://github.com/DawidAdamski/kaleta/commit/8e3d6cec305aede823b7f9625d0a52ef634a2464))
* **deploy:** run the container images as a non-root user (F-6) ([c5e3809](https://github.com/DawidAdamski/kaleta/commit/c5e3809bd7c5cc2dda5ac8c2b8b4bd67d2a41d7b))
* **errors:** give KaletaError a translation key so toasts localize ([463579e](https://github.com/DawidAdamski/kaleta/commit/463579e53a2073704cd6492e4eb5f07c072ceb00))
* **errors:** give KaletaError a translation key so toasts localize (KAL-ERR-001) ([4ef36c9](https://github.com/DawidAdamski/kaleta/commit/4ef36c9978d4d4629efc061c4e6ca37e99159b5c))
* **errors:** localize household_service error toasts ([6ae8555](https://github.com/DawidAdamski/kaleta/commit/6ae855591be73c62ce918f10df4ada3a99319e78))
* **errors:** localize household_service error toasts (KAL-ERR-006) ([5d1142a](https://github.com/DawidAdamski/kaleta/commit/5d1142a010af57d3c0ba7ef8097500175e5cc85f))
* **errors:** localize irregular_item_service error toasts ([1ea80f7](https://github.com/DawidAdamski/kaleta/commit/1ea80f799e95cf1ddaa29ae527e7f9e8ad0997e9))
* **errors:** localize irregular_item_service error toasts (KAL-ERR-003) ([e5a39f8](https://github.com/DawidAdamski/kaleta/commit/e5a39f87fd400499e7ad43fa8b41c1b9c0010eb5))
* **errors:** localize long-tail service error raises (KAL-ERR-010) ([0301f8c](https://github.com/DawidAdamski/kaleta/commit/0301f8cad18c8926d4bc6f43aafa0d1bbda09d14))
* **errors:** localize MFA, hosted-MFA & API-token error toasts ([163ed95](https://github.com/DawidAdamski/kaleta/commit/163ed956ea7a47a13b01213e1c81bfde24283301))
* **errors:** localize reserve-fund, gift, salary & personal-loan error toasts ([dda4826](https://github.com/DawidAdamski/kaleta/commit/dda4826ec320b70108a80b32977a5831a4c5f0e9))
* **errors:** localize reserve-fund, gift, salary & personal-loan error toasts (KAL-ERR-004) ([01c9307](https://github.com/DawidAdamski/kaleta/commit/01c930791b103cb169c5852cf65e481dea4a4216))
* **errors:** localize rule, subscription, category, budget & account error toasts ([67792f6](https://github.com/DawidAdamski/kaleta/commit/67792f625d8cdec74b969dffe243c55450775c88))
* **errors:** localize rule, subscription, category, budget & account error toasts (KAL-ERR-005) ([1050807](https://github.com/DawidAdamski/kaleta/commit/1050807e2155340338a6b1f850096d4cf9513af9))
* **errors:** localize the toast-reaching admin/infra error raises ([3eaf8ac](https://github.com/DawidAdamski/kaleta/commit/3eaf8ac603a25280ce3a76f0e7a00f1b54b2c576))
* **errors:** localize the toast-reaching admin/infra error raises (KAL-ERR-009) ([055e754](https://github.com/DawidAdamski/kaleta/commit/055e754d57d6518d520721930e26847cf8c92926))
* **errors:** localize the toast-reaching key & local-identity error raises ([f0ea0b2](https://github.com/DawidAdamski/kaleta/commit/f0ea0b25516c59f746efd84d8275963d2118f844))
* **errors:** localize the toast-reaching key & local-identity error raises (KAL-ERR-008) ([47ec2b6](https://github.com/DawidAdamski/kaleta/commit/47ec2b61a5a9767169ef5cb9c55ec9c8ab48d985))
* **errors:** localize the toast-reaching long-tail error raises ([baa18df](https://github.com/DawidAdamski/kaleta/commit/baa18dfe281d172fdcdaa4c6ad1fc68f00b0fa67))
* **errors:** localize the toast-reaching MFA & API-token error raises (KAL-ERR-007) ([5fd17d0](https://github.com/DawidAdamski/kaleta/commit/5fd17d0c86012dcdc985e2ef69489340664f2d39))
* **errors:** localize transaction_service error toasts ([806f9e1](https://github.com/DawidAdamski/kaleta/commit/806f9e19de6e46f92f3f5b0ff18ccc176079be7e))
* **errors:** localize transaction_service error toasts ([4c9f468](https://github.com/DawidAdamski/kaleta/commit/4c9f4685250427700b3d9a0286a98c4dc5eb0cb0))
* **gifts:** maintain the gift list — person, occasion, amount ([#21](https://github.com/DawidAdamski/kaleta/issues/21)) ([3186de2](https://github.com/DawidAdamski/kaleta/commit/3186de264a3216d06bd688a17a9507a77b498311))
* **gifts:** maintain the gift list — person, occasion, amount ([#21](https://github.com/DawidAdamski/kaleta/issues/21)) ([8148332](https://github.com/DawidAdamski/kaleta/commit/8148332e7b06022c8fa61527593da92341c9d294))
* **gifts:** mark a gift bought by linking the transaction that paid for it ([#21](https://github.com/DawidAdamski/kaleta/issues/21)) ([e13fd03](https://github.com/DawidAdamski/kaleta/commit/e13fd031e0a71d75aa4f0ddaa494f3dc028f67ad))
* **gifts:** mark a gift bought by linking the transaction that paid for it ([#21](https://github.com/DawidAdamski/kaleta/issues/21)) ([7962a65](https://github.com/DawidAdamski/kaleta/commit/7962a65ba27f62b885e0f226f85dc155753741c4))
* **gifts:** surface the yearly gift total on the irregular fund ([#21](https://github.com/DawidAdamski/kaleta/issues/21)) ([0629622](https://github.com/DawidAdamski/kaleta/commit/0629622b263cdfbdf7260acfdecef8770ce7fb61))
* **gifts:** surface the yearly gift total on the irregular fund ([#21](https://github.com/DawidAdamski/kaleta/issues/21)) ([2449279](https://github.com/DawidAdamski/kaleta/commit/24492791096326add40aa4d48fe8bbeda2e56bd9))
* **import:** cap upload size server-side (F-4) ([c50cf52](https://github.com/DawidAdamski/kaleta/commit/c50cf526c5ef7f23fbbb53bbadfe6cf2a8e6d2d8))
* **import:** cap upload size server-side, independent of the browser limit ([224b72c](https://github.com/DawidAdamski/kaleta/commit/224b72c48e840dec1f35eda48f6dc6231fd25ffb))
* **reports:** emit dimension/metric keys, resolve display strings via t() ([49f491b](https://github.com/DawidAdamski/kaleta/commit/49f491b56ea5aac40e134b7c9fc1864ed5f8b587))
* **reports:** emit dimension/metric keys, resolve display strings via t() (KAL-RPT-012) ([79a9c70](https://github.com/DawidAdamski/kaleta/commit/79a9c700b647a58a13d56a5f7db469a9646c4efd))
* **security:** add a schemathesis API-fuzzing runner (Slice 2b) ([35d8dd1](https://github.com/DawidAdamski/kaleta/commit/35d8dd1b1cef3a5dd7d8187917168cc5b2eafac3))
* **security:** add a schemathesis API-fuzzing runner (Slice 2b) ([91f74d5](https://github.com/DawidAdamski/kaleta/commit/91f74d58ffbdb6a9a7cc641685ceea046386c1ab))
* **security:** add an OWASP ZAP baseline runner (Slice 2a) ([0493ba3](https://github.com/DawidAdamski/kaleta/commit/0493ba3e71359649f55dcaa18fb914b607ab2178))
* **security:** add an OWASP ZAP baseline runner (Slice 2a) ([37b3d00](https://github.com/DawidAdamski/kaleta/commit/37b3d0091a64e7925d567a4684362520a09d1136))
* **security:** add Trivy scanner (fs/config/secret/image) ([5f72539](https://github.com/DawidAdamski/kaleta/commit/5f72539b704ff7ea37dd487f613c811938772f27))
* **security:** add Trivy scanner (fs/config/secret/image) to the toolbox ([ef15bc1](https://github.com/DawidAdamski/kaleta/commit/ef15bc1c145846a47608bf550394e91987a1338b))
* **security:** run the server-less security checks nightly in CI ([46c7c1e](https://github.com/DawidAdamski/kaleta/commit/46c7c1ed444455547d40c4c4d7f95899f36f94d9))
* **security:** run the server-less security checks nightly in CI ([a39b390](https://github.com/DawidAdamski/kaleta/commit/a39b390fbc73bbd3ac98644852a3b5063a300417))
* **security:** set security response headers on the web app (F-8) ([1666b65](https://github.com/DawidAdamski/kaleta/commit/1666b653292d9961ee53603dd98254e705436730))
* **security:** set security response headers on the web app (F-8) ([011ff89](https://github.com/DawidAdamski/kaleta/commit/011ff895e1a2f006540fe536e3f4084e60b99743))
* **security:** ship the Spectre site-isolation response headers (F-8 follow-up) ([da2626d](https://github.com/DawidAdamski/kaleta/commit/da2626dd88d885af5030699db2a14a66854c51f9))
* **security:** ship the Spectre site-isolation response headers (F-8) ([4416ff0](https://github.com/DawidAdamski/kaleta/commit/4416ff0eb2d47a59a3ccfc545fce99a720193eae))
* **settings:** one example-data panel, not two ([e9f2a67](https://github.com/DawidAdamski/kaleta/commit/e9f2a67be5f08f5de3efe68e4433ae845aa0b367))
* **settings:** one example-data panel, not two ([751d3ab](https://github.com/DawidAdamski/kaleta/commit/751d3abc6b6c9c6e92042cf666e3a99bd454c785))
* **settings:** throttle the manual "Fetch NBP rates" button per instance ([c51418d](https://github.com/DawidAdamski/kaleta/commit/c51418d47120ee40d9da4b9851c2c57b7aab8090))
* **settings:** throttle the manual "Fetch NBP rates" button per instance ([a569135](https://github.com/DawidAdamski/kaleta/commit/a569135a01ec23c6789301c11ed37326d268b45c))


### Bug Fixes

* **auth:** forget the disabled member's own revocation entry, not the admin's ([a07e4f4](https://github.com/DawidAdamski/kaleta/commit/a07e4f4b36af7f18a29c6c550f361e2bf3e06286))
* **auth:** forget the disabled member's own tenant watermark ([73d440b](https://github.com/DawidAdamski/kaleta/commit/73d440b06db7bcc25b0390a52cdc4138eb8657cc))
* **auth:** hand the MFA challenge over the URL, not a racy storage write ([0590398](https://github.com/DawidAdamski/kaleta/commit/0590398069b569fdef2154dbe01b7794f844f222))
* **auth:** hand the MFA challenge over the URL, not a racy storage write ([9f38d60](https://github.com/DawidAdamski/kaleta/commit/9f38d60917d1bc4dc66e1643645affc03585cc8a))
* **auth:** surface a toast when the login/MFA rate limiter backend is down ([477eefd](https://github.com/DawidAdamski/kaleta/commit/477eefddaccca5780f2bb93c435a205c68c57a6d))
* **auth:** throttle password sign-in per e-mail, not only per client address ([00c814b](https://github.com/DawidAdamski/kaleta/commit/00c814b121c7b286181884a90fe2982429ef65cc))
* **auth:** throttle password sign-in per e-mail, not only per client address (KAL-AUTH-042) ([7b320b2](https://github.com/DawidAdamski/kaleta/commit/7b320b2ab5ebd9130401f92394a5758cd5f1d9ff))
* **auth:** toast instead of a dead click when the rate limiter backend is down ([251261b](https://github.com/DawidAdamski/kaleta/commit/251261b5091c5c2ac00cf298195e746c9db0dd1c))
* **budget-builder:** register Apply-confirm handler once ([448fb00](https://github.com/DawidAdamski/kaleta/commit/448fb00d19199b3044b6679336f22f52db39aef4))
* **budget-builder:** register the Apply-confirm handler once ([d3d5656](https://github.com/DawidAdamski/kaleta/commit/d3d5656b0745aae5ab17d79cdaf52cfdf8105a0f))
* **budgets:** actually sort bulk_upsert rows; refresh yearly upsert return ([87529d4](https://github.com/DawidAdamski/kaleta/commit/87529d4452f9820299ca4710c26054fe694d0bd4))
* **budgets:** honour ?year= on its own in GET /api/v1/budgets ([9f37641](https://github.com/DawidAdamski/kaleta/commit/9f37641a52b72574e18b55a4370f1a534322bc64))
* **budgets:** honour ?year= on its own in GET /api/v1/budgets ([30cd905](https://github.com/DawidAdamski/kaleta/commit/30cd905a0237ea52614f0bc6cbeea64e7b9a3ca2))
* **budgets:** make Budget Builder Apply concurrency-idempotent (KAL-BBD-002) ([f8c861f](https://github.com/DawidAdamski/kaleta/commit/f8c861f92d703ab553e90803ff364396bc1fcc7c))
* **budgets:** make bulk_upsert concurrency-idempotent via ON CONFLICT ([d1559a6](https://github.com/DawidAdamski/kaleta/commit/d1559a6378502f3f07fc06e87cda3fde992d0ac1))
* **budgets:** make YearlyPlan.upsert atomic too; test apply end-to-end ([4701ce0](https://github.com/DawidAdamski/kaleta/commit/4701ce04081735de846d1585fb279d802b963971))
* **config:** report settings validation errors by message only, never input ([3c3b8f2](https://github.com/DawidAdamski/kaleta/commit/3c3b8f27006f386dea4e67aa73b6de6629acc808))
* **dashboard:** clip long account names to their tile ([#19](https://github.com/DawidAdamski/kaleta/issues/19)) ([1d1c67e](https://github.com/DawidAdamski/kaleta/commit/1d1c67e4a78a803e8a9b8dfd0ee8b02960e055a9))
* **dashboard:** clip long account names to their tile ([#19](https://github.com/DawidAdamski/kaleta/issues/19)) ([88f489d](https://github.com/DawidAdamski/kaleta/commit/88f489d6e0c10fc8a8ae685583c546256ce863f5))
* **dashboard:** make desktop "Needs attention" banner items keyboard-reachable ([f8579f1](https://github.com/DawidAdamski/kaleta/commit/f8579f18cd973f7ee224e3a1a8fc0689f69319ef))
* **dashboard:** make the "Needs attention" banner items keyboard-reachable (KAL-DSH-012) ([b7432f5](https://github.com/DawidAdamski/kaleta/commit/b7432f5b1816a854380956897af6657f752402a4))
* **dashboard:** sign recent-transactions transfer legs by direction ([e5a3039](https://github.com/DawidAdamski/kaleta/commit/e5a3039eb78d21963ec5d52eec1b94f44603e3d3))
* **dashboard:** sign recent-transactions transfer legs by direction ([2dc13ba](https://github.com/DawidAdamski/kaleta/commit/2dc13ba91b010dad55c84a32ca214d9d6aabbd09))
* **db:** reconcile model/DB drift so alembic check is clean ([77f2232](https://github.com/DawidAdamski/kaleta/commit/77f223211725d7c5fa25b460674362c14c7680b5))
* **db:** reconcile model/schema drift so alembic check is clean ([c47d6f9](https://github.com/DawidAdamski/kaleta/commit/c47d6f954ed4e2840b5515073bf073a2bbc91ade))
* **debts:** exclude loan-linked transactions from all spending/income readers ([dda0dbe](https://github.com/DawidAdamski/kaleta/commit/dda0dbeae33950edcd2cfc05879b94ccee0ea75d))
* **debts:** exclude loan-linked transactions from all spending/income readers (KAL-DBT-005) ([67d71ea](https://github.com/DawidAdamski/kaleta/commit/67d71ea448e416ed46be3af495fb00cf38723ec7))
* **dedupe:** carry fund/plan links to keeper when merging duplicate transactions ([c566d24](https://github.com/DawidAdamski/kaleta/commit/c566d2457a4845e9b1d378513d2f6bc87ef25b52))
* **dedupe:** carry gift_id to the keeper on merge (KAL-DUP-003) ([ccc5ac1](https://github.com/DawidAdamski/kaleta/commit/ccc5ac19091c274187ad6d6bfa1319e8651af7c6))
* **dedupe:** carry gift_id to the keeper on merge (KAL-DUP-003) ([2667be4](https://github.com/DawidAdamski/kaleta/commit/2667be43bdda6cd3b35c1427f11eae3e54d9ef3d))
* **dedupe:** keep fund/plan links when merging duplicate transactions ([f90b5b6](https://github.com/DawidAdamski/kaleta/commit/f90b5b6c0ad70c78fd4aaf1fc2eb82b922cb4b90))
* **deps:** bump aiohttp to 3.14.5 to clear three advisories ([080b08b](https://github.com/DawidAdamski/kaleta/commit/080b08b41838ded50f08a050bd4ecd560fbdd346))
* **deps:** bump aiohttp to 3.14.5 to clear three advisories ([965e961](https://github.com/DawidAdamski/kaleta/commit/965e961e6eda3c1caf13cbc67f4ac7ae331d5748))
* **funds:** re-planning the funding transfer refreshes it instead of duplicating ([697858c](https://github.com/DawidAdamski/kaleta/commit/697858c7c41acb4202ecce7640c3be121a760c13))
* **funds:** re-planning the funding transfer refreshes it instead of duplicating ([272c71f](https://github.com/DawidAdamski/kaleta/commit/272c71fcc60a524f468b93bada8b79772a22b148))
* **gifts:** address review — buyable query filter, re-link guard ([f1f49df](https://github.com/DawidAdamski/kaleta/commit/f1f49dfc7fa1eef88c63c1b10a564be38a0cf80d))
* **gifts:** address review — clear_all coverage, validation, NotFoundError ([52a086f](https://github.com/DawidAdamski/kaleta/commit/52a086fefdacb3955b0a8c63e0a3d6546c9235ba))
* **import:** no currency-mismatch warning when the file currency is unknown ([4e4b7b5](https://github.com/DawidAdamski/kaleta/commit/4e4b7b559b36455288e6f126cb72906df94aa0ea))
* **import:** suppress currency warning when file currency is unknown ([932070c](https://github.com/DawidAdamski/kaleta/commit/932070c46dd8de9017e81d9b03b6bdd7d4206b00))
* **ledger:** sign a transfer leg by its direction, not its type ([ebb4f22](https://github.com/DawidAdamski/kaleta/commit/ebb4f228221232ffe22da5e16d0a9601ad3a3340))
* **ledger:** sign each transfer leg by its direction ([0b887aa](https://github.com/DawidAdamski/kaleta/commit/0b887aac22add7885858403d1302da0d001c9858))
* **models:** make audit_log.timestamp and personal_loans.settled_at tz-aware ([f962f26](https://github.com/DawidAdamski/kaleta/commit/f962f2663650ecee2f9bfe7ac331dafe2fc5dcca))
* **models:** make audit_log.timestamp and personal_loans.settled_at tz-aware ([f75d42e](https://github.com/DawidAdamski/kaleta/commit/f75d42e27b2a89ed806be98f4e7cf2070eb4eb95))
* **money-flow:** draw transfer ribbons by transfer_direction, not id order ([c631f37](https://github.com/DawidAdamski/kaleta/commit/c631f3755e5cc6bf123999546a4b1cb3a44606eb))
* **moneyflow:** draw transfer ribbons by stored direction, not id order ([9ce685d](https://github.com/DawidAdamski/kaleta/commit/9ce685de32c0fb8d0d89018eb8afc53401b2f2da))
* **reports:** a trend report says "all periods", not a top-N it ignores ([0f4baab](https://github.com/DawidAdamski/kaleta/commit/0f4baaba8b775eddb43eab2f2e59591b774911f2))
* **reports:** trend report says "all periods", not a top-N it ignores ([f4e6c0d](https://github.com/DawidAdamski/kaleta/commit/f4e6c0d6fee3e76dbe2a4741c1dc9f80d1c6ab87))
* **rules:** category picker shows the tree, not flat names ([d8a7c68](https://github.com/DawidAdamski/kaleta/commit/d8a7c682020225ba9067eb5c49e9f12fab569c46))
* **rules:** category picker shows the tree, not flat names ([#23](https://github.com/DawidAdamski/kaleta/issues/23)) ([d1054f3](https://github.com/DawidAdamski/kaleta/commit/d1054f39b74761c306e75245e83fed20cfa23ba3))
* **safety-funds:** restore Emergency fields when switching fund type back ([#20](https://github.com/DawidAdamski/kaleta/issues/20)) ([8d3339c](https://github.com/DawidAdamski/kaleta/commit/8d3339cc5eed961886094ecd094305536ce010c7))
* **safety-funds:** restore emergency fields when switching kind back ([60eb136](https://github.com/DawidAdamski/kaleta/commit/60eb136cbfc77fd9bf1080f65b1dd9a3f26f3cca))
* **salary:** post both legs of a planned salary transfer ([371267a](https://github.com/DawidAdamski/kaleta/commit/371267a8b56c4202b2f57fcfb536c5c05e81bd95))
* **salary:** post both legs of a planned salary transfer ([d248356](https://github.com/DawidAdamski/kaleta/commit/d24835657a6fa5ba02189465c5e6dce36905863c))
* **seed:** skip canonical tags already present on a fresh family ([28ea1fb](https://github.com/DawidAdamski/kaleta/commit/28ea1fba03e50b7de9280510130c25a22beb579a))
* **seed:** skip canonical tags already present on a fresh family ([b80b5f4](https://github.com/DawidAdamski/kaleta/commit/b80b5f4bd1876e4f1bf1be955ab7a2098983e3bf))
* **settings:** report config validation errors by message only, never the input ([81a112d](https://github.com/DawidAdamski/kaleta/commit/81a112d10df5df1625466b6b4b8cc41827aa814f))
* **setup:** rebuild sync DB URL structurally instead of string-replacing the driver ([f693086](https://github.com/DawidAdamski/kaleta/commit/f693086dd0f5b0e4d25dd03718e2bfe5f6ccb0d7))
* **setup:** rebuild sync DB URL structurally, not by str.replace ([2cd1582](https://github.com/DawidAdamski/kaleta/commit/2cd1582bb84c768fd8e91c048516d73cca718c0f))
* **subscriptions:** settle due cancellations on a schedule, not only on page open ([80676f5](https://github.com/DawidAdamski/kaleta/commit/80676f5b6ca0aae9bfeb6b0ebc520274380256ef))
* **subscriptions:** settle due cancellations on a schedule, not only on page open (KAL-SUB-010) ([b47f268](https://github.com/DawidAdamski/kaleta/commit/b47f268b4143d7d6a7f472706aed901605641f11))
* **test:** await the slot repaint in the trend/top-N e2e ([b07a3a4](https://github.com/DawidAdamski/kaleta/commit/b07a3a4ae9534d1510da3857b7a7cd24afb4e9c2))
* **views:** log the swallowed rate-limiter clear() error with exc_info ([24ed3b1](https://github.com/DawidAdamski/kaleta/commit/24ed3b12ea1ddab053e907a15528d949e1d7a5d1))
* **wizard:** project a subscription the way the panel normalises it ([5e7518f](https://github.com/DawidAdamski/kaleta/commit/5e7518f730572817440aaf19a54f5610caceb32f))
* **wizard:** project a subscription the way the panel normalises it ([#21](https://github.com/DawidAdamski/kaleta/issues/21)) ([9b2907c](https://github.com/DawidAdamski/kaleta/commit/9b2907cb89e83a12bdd18fc02832b448fd50bdbd))


### Performance Improvements

* **mfa:** run argon2 hashing off the event loop ([3cc67c0](https://github.com/DawidAdamski/kaleta/commit/3cc67c0b8ed2f3c5698b5d0e4685fd0954471a16))
* **mfa:** run argon2 hashing/verification off the event loop ([f3c71c7](https://github.com/DawidAdamski/kaleta/commit/f3c71c7b23fc789a8987e4ebf837ccdb3d0146cd))

## [0.7.0](https://github.com/DawidAdamski/kaleta/compare/v0.6.0...v0.7.0) (2026-10-15)


### Features

* **settings:** choose the ledger's default page size and grouping ([9a96300](https://github.com/DawidAdamski/kaleta/commit/9a96300c4273e7fe59daf8865f5370921cdca1a6))
* **settings:** default ledger page size (50/100/200/500) and grouping ([b0ac0f9](https://github.com/DawidAdamski/kaleta/commit/b0ac0f9e9717cbd270711cce9d498addfd1ed18e))
* **transactions:** bulk change-category for selected rows ([#17](https://github.com/DawidAdamski/kaleta/issues/17)) ([d62b9d3](https://github.com/DawidAdamski/kaleta/commit/d62b9d3e4d84053221e37094e759d4b6dcb5b3b4))
* **transactions:** bulk change-category for selected rows ([#17](https://github.com/DawidAdamski/kaleta/issues/17)) ([8a48ec0](https://github.com/DawidAdamski/kaleta/commit/8a48ec00dc3978180a88d65b3473aa0259af3047))


### Bug Fixes

* **transactions:** clamp page to last non-empty page after in-place refresh ([f46abc6](https://github.com/DawidAdamski/kaleta/commit/f46abc6397202cde914e7b961c5e8c76988688ce))
* **transactions:** drop debounce, keep the render-token guard as the fix ([63e02b3](https://github.com/DawidAdamski/kaleta/commit/63e02b36b4c91d2602ae30c24f2e2e3e16f60b75))
* **transactions:** editing a row keeps the reader's place ([#22](https://github.com/DawidAdamski/kaleta/issues/22)) ([2d44fc4](https://github.com/DawidAdamski/kaleta/commit/2d44fc426bc538653dc6c09718ee48804dc71ae8))
* **transactions:** editing a row keeps the reader's place ([#22](https://github.com/DawidAdamski/kaleta/issues/22)) ([6a8d81a](https://github.com/DawidAdamski/kaleta/commit/6a8d81aee6651dd2944a6e7c0e0550e70dce7222))
* **transactions:** stop the ledger search painting a second table ([07de5c9](https://github.com/DawidAdamski/kaleta/commit/07de5c927e284cad78bde4d8e6d1cf0a8af9c03e))
* **transactions:** stop the ledger search painting a second table ([ca9e23a](https://github.com/DawidAdamski/kaleta/commit/ca9e23acb149615a65810324b9bd76f0204842c9))

## [0.6.0](https://github.com/DawidAdamski/kaleta/compare/v0.5.0...v0.6.0) (2026-10-14)


### Features

* **deploy:** a real multi-replica path in the Helm chart ([d2eb5ca](https://github.com/DawidAdamski/kaleta/commit/d2eb5ca297217e21510e3aa84f0a186b8403d1cc))
* **deploy:** a real multi-replica path in the Helm chart ([2dc4f31](https://github.com/DawidAdamski/kaleta/commit/2dc4f314e154eb4870576a8eb7d4212c1f4d9779))
* **deploy:** secure the multi-replica chart path (review nits) ([f5aeeee](https://github.com/DawidAdamski/kaleta/commit/f5aeeee8dedaaf5c3f2bed69a461a4f8c5c86f55))
* **import:** link the settings step to the saved import rules ([#10](https://github.com/DawidAdamski/kaleta/issues/10)) ([3359d8a](https://github.com/DawidAdamski/kaleta/commit/3359d8af4cd291013d0a8e4b62f50a278ddeafce))
* **import:** link the settings step to the saved import rules ([#10](https://github.com/DawidAdamski/kaleta/issues/10)) ([113a341](https://github.com/DawidAdamski/kaleta/commit/113a34147a8974865e41981a456e7bdf481df48e))
* **import:** open the import wizard on Format with a selectable page-default format ([#7](https://github.com/DawidAdamski/kaleta/issues/7) follow-up) ([6b85da4](https://github.com/DawidAdamski/kaleta/commit/6b85da4885763099b3ca6323a08c17d5bdacb2d4))
* **import:** open the wizard on Format with a selectable page-default format ([ca03b44](https://github.com/DawidAdamski/kaleta/commit/ca03b445372c218d2f44f8a19c538bfedd07879e))
* **theme:** give every button a press affordance ([#13](https://github.com/DawidAdamski/kaleta/issues/13)) ([3bd35b1](https://github.com/DawidAdamski/kaleta/commit/3bd35b1eb41d752cc03957726dff00f2ce266bd7))
* **theme:** give every button a press affordance ([#13](https://github.com/DawidAdamski/kaleta/issues/13)) ([3f35118](https://github.com/DawidAdamski/kaleta/commit/3f35118e85312d6b7aa54695bf91a4d5236ec22b))


### Bug Fixes

* **accounts:** make the active "group by" option visibly selected ([010486d](https://github.com/DawidAdamski/kaleta/commit/010486d8f6000a8fc8551b193f6a7eb48c50fc09))
* **accounts:** show which "group by" option is active ([#2](https://github.com/DawidAdamski/kaleta/issues/2)) ([2299e71](https://github.com/DawidAdamski/kaleta/commit/2299e7196968cf305b83e0f29bd2be226ea0b6b6))
* **categories:** add-subcategory no longer saves a root category ([1a3805d](https://github.com/DawidAdamski/kaleta/commit/1a3805dffe10702742a8f19edb52c005d6602f15))
* **categories:** add-subcategory no longer saves a root category ([f1b6794](https://github.com/DawidAdamski/kaleta/commit/f1b6794f098819731fa603a6e915291920eae214))
* **categories:** protect the Subscriptions root from deletion ([d433c3b](https://github.com/DawidAdamski/kaleta/commit/d433c3be9de1d8e109580d0af2fa7b17075c096a))
* **categories:** protect the Subscriptions root from deletion ([e47833f](https://github.com/DawidAdamski/kaleta/commit/e47833f3de942586d813be7ec0ff1bcb57c2e063))
* **import:** cap the transfer-suggestions list and pin accept-all ([#8](https://github.com/DawidAdamski/kaleta/issues/8)) ([e026015](https://github.com/DawidAdamski/kaleta/commit/e02601536c5b533b3c2bc4e44d848a9873be53ea))
* **import:** cap the transfer-suggestions list and pin accept-all ([#8](https://github.com/DawidAdamski/kaleta/issues/8)) ([ce717a3](https://github.com/DawidAdamski/kaleta/commit/ce717a3d3de9f37b7e429d12d8b0099790414aef))
* **import:** don't repaint when re-clicking the step already on screen ([1c402f7](https://github.com/DawidAdamski/kaleta/commit/1c402f7d6960cd94efd2069a2923257052566a2a))
* **import:** guard transfer accept/dismiss against a double-click ([8da128a](https://github.com/DawidAdamski/kaleta/commit/8da128a6c0cf6a500eec425f54db8e11d15d23a9))
* **import:** guard transfer accept/dismiss against a double-click ([1e6cb2b](https://github.com/DawidAdamski/kaleta/commit/1e6cb2b28e005a1fdd83cf1e93753fbb968c45d9))
* **import:** re-clicking the current step wedged wizard navigation ([#257](https://github.com/DawidAdamski/kaleta/issues/257) regression) ([31afd07](https://github.com/DawidAdamski/kaleta/commit/31afd072c50152089e5540436bf0ce6934452769))
* **import:** surface import history — open the reference expanders by default ([3f1a401](https://github.com/DawidAdamski/kaleta/commit/3f1a4014eaf1b4ad69bd6468a897c6640cf7107d))
* **import:** surface import history ([#7](https://github.com/DawidAdamski/kaleta/issues/7)) ([c1a0553](https://github.com/DawidAdamski/kaleta/commit/c1a05534f6df68e41c29c945b3e7c73ccf053847))
* **planned:** narrow the category list to the selected type ([ecb508b](https://github.com/DawidAdamski/kaleta/commit/ecb508bc3f20132fb19006b518fa4055aa7f33ae))
* **planned:** narrow the category list to the selected type ([16140d4](https://github.com/DawidAdamski/kaleta/commit/16140d474b43a50cf30ea81189bb9194c6d30f52))
* **transactions:** tooltip on truncated ledger cells ([1f87692](https://github.com/DawidAdamski/kaleta/commit/1f876927b24b13f2e935f4d628251430f12496e4))
* **transactions:** tooltip on truncated ledger cells ([#9](https://github.com/DawidAdamski/kaleta/issues/9)) ([1d4e1fb](https://github.com/DawidAdamski/kaleta/commit/1d4e1fb4d31a8ffec52328b4659e79574ac28d1b))
* **upload:** migrate upload handlers to NiceGUI 3.x event API ([8071606](https://github.com/DawidAdamski/kaleta/commit/80716066052b7ccaf5ed7d2b407121db0c1ecb04))
* **upload:** migrate upload handlers to the NiceGUI 3.x event API ([4016cd2](https://github.com/DawidAdamski/kaleta/commit/4016cd2078e67012dba79b167aefd74f970b6efd))

## [0.5.0](https://github.com/DawidAdamski/kaleta/compare/v0.4.0...v0.5.0) (2026-10-13)


### Features

* **deploy:** harden the migration lock + test (review nits) ([6531ae8](https://github.com/DawidAdamski/kaleta/commit/6531ae815504b387683a2b9f6b33f1b0c8f90607))
* **deploy:** serialise startup migration with a Postgres advisory lock ([7621dc6](https://github.com/DawidAdamski/kaleta/commit/7621dc6dfb739f6991b503c9273f7ea4360c1463))
* **deploy:** serialise startup migration with a Postgres advisory lock ([7e19198](https://github.com/DawidAdamski/kaleta/commit/7e191986c6309b41df8d293a851fbcb2d9ae713f))

## [0.4.0](https://github.com/DawidAdamski/kaleta/compare/v0.3.0...v0.4.0) (2026-10-13)


### Features

* **deploy:** complete the k3s Helm chart + docs (deploy-k3s Slice 1) ([44aa03c](https://github.com/DawidAdamski/kaleta/commit/44aa03cbf4b3754540ff6d4487696c40244d31a6))
* **deploy:** k3s Helm chart + docs (deploy-k3s Slice 1) ([d2893ef](https://github.com/DawidAdamski/kaleta/commit/d2893ef035edc04f947925f7ce180089b0512094))


### Bug Fixes

* **deploy:** component selector + restore runbook (chart review) ([30542c0](https://github.com/DawidAdamski/kaleta/commit/30542c0a788c15fd773367287b1c2c3f5e6a1ca8))

## [0.3.0](https://github.com/DawidAdamski/kaleta/compare/v0.2.0...v0.3.0) (2026-10-12)


### Features

* **categories:** template picker — build the tree from who you are ([be9d6e0](https://github.com/DawidAdamski/kaleta/commit/be9d6e0d17f50dc408c91e0f5a046befa7494313))
* **categories:** template picker — build the tree from who you are (Slice 2) ([08ebfdb](https://github.com/DawidAdamski/kaleta/commit/08ebfdb78396b31fd1c0f3034b1422f92c940ef6))
* **security:** assessment recon + static pass (Slice 1) ([85226e4](https://github.com/DawidAdamski/kaleta/commit/85226e46b5e4a6a6c6974f20d135d54ce11710be))
* **security:** assessment recon + static pass (Slice 1) ([5f9444b](https://github.com/DawidAdamski/kaleta/commit/5f9444bfd22cfba9d9e20fc8ff8a18551db23140))
* **subscriptions:** file under a purpose child and re-file history (Part B) ([30c0fb7](https://github.com/DawidAdamski/kaleta/commit/30c0fb7b6913199a69a12ad89fd3ec25a11db50f))
* **subscriptions:** file under a purpose child and re-file history (Part B) ([057c75f](https://github.com/DawidAdamski/kaleta/commit/057c75fe7b18bb2fa60b5bf5db3a928e88a19a26))

## [0.2.0](https://github.com/DawidAdamski/kaleta/compare/v0.1.0...v0.2.0) (2026-10-12)


### Features

* **categories:** template engine — build your tree from who you are ([440797c](https://github.com/DawidAdamski/kaleta/commit/440797cd9c5e1de8871d2369029cb27eb7a98cd5))
* **categories:** template engine — build your tree from who you are (Slice 1) ([1ebd845](https://github.com/DawidAdamski/kaleta/commit/1ebd845555d3eac068b9ccf37216ee3913fe7bba))

## Changelog

All notable changes to Kaleta are recorded here. This file is maintained
automatically by [release-please](https://github.com/googleapis/release-please)
from the conventional-commit history — do not edit it by hand. Each release is
cut by merging the standing "release PR"; that creates the matching `vX.Y.Z`
git tag, which is the source the app's version is derived from (hatch-vcs).
