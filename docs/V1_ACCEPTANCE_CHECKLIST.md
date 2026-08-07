# Version 1 Acceptance Checklist

- [ ] Database migration succeeds.
- [ ] Telegram bot starts and responds to the configured operator.
- [ ] System Status reports Database OK.
- [ ] System Status reports RBXCrate API OK.
- [ ] A Draft order can be created with a manual Place ID.
- [ ] Payment confirmation starts Purchasing when suitable stock exists.
- [ ] Marketplace synchronization completes the ClientOrder.
- [ ] A Completed order rejects subsequent modification.
- [ ] Recovery repairs an interrupted Purchasing order.
- [ ] Backup creation and isolated restoration are tested.
- [ ] Dry-run mode completes an end-to-end order without a live RBXCrate request.
- [ ] Ruff formatting and linting pass.
- [ ] Unit and PostgreSQL integration tests pass.
