# Changelog

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
