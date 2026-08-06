# BUSINESS RULES

Document

BUSINESS_RULES

Version

1.0

Status

Final Draft

---

# 1. PURPOSE

This document defines all business rules governing SensFlow Version 1.

Business Rules have the highest priority during implementation.

If implementation contradicts these rules, the implementation SHALL be considered incorrect.

---

# 2. GENERAL PRINCIPLES

BR-2.1

Business correctness has higher priority than execution speed.

BR-2.2

Every Client Order SHALL belong to exactly one Customer.

BR-2.3

Completed Orders SHALL preserve complete history.

BR-2.4

Business history SHALL never be automatically deleted.

BR-2.5

Automation SHALL never create duplicate purchases.

---

# 3. CUSTOMER RULES

BR-3.1

One Roblox account SHALL correspond to one Customer.

BR-3.2

Customer identity SHALL remain unchanged after username changes.

BR-3.3

Customers SHALL be created automatically.

BR-3.4

Operators MAY manually update Place ID.

BR-3.5

Customer history SHALL remain permanently available.

---

# 4. CLIENT ORDER RULES

BR-4.1

Every Client Order SHALL belong to one Customer.

BR-4.2

Every Client Order SHALL contain one Requested Robux value.

BR-4.3

Client Orders SHALL always have exactly one current status.

BR-4.4

Only valid state transitions are permitted.

BR-4.5

Completed Orders SHALL become read-only.

BR-4.6

Cancelled Orders SHALL preserve complete history.

---

# 5. PAYMENT RULES

BR-5.1

A Client Order SHALL NOT enter Purchasing before payment confirmation.

BR-5.2

After payment confirmation:

If suitable Marketplace Stock exists

↓

Purchasing

Otherwise

↓

PreOrder

BR-5.3

The operator SHALL NOT manually override this decision.

---

# 6. MARKETPLACE RULES

BR-6.1

Marketplace Orders SHALL exist only to execute Client Orders.

BR-6.2

Only one Marketplace Order MAY be active for one Client Order.

BR-6.3

Marketplace Orders MAY be recreated unlimited times until completion.

BR-6.4

Marketplace Orders SHALL NOT exist after Client Order completion.

---

# 7. AUTOMATION RULES

BR-7.1

Automatic Reorder SHALL only operate on Purchasing Orders.

BR-7.2

Automatic Reorder SHALL stop immediately after purchase completion.

BR-7.3

Manual Reorder SHALL follow the same workflow as Automatic Reorder.

BR-7.4

Automation SHALL never modify Customer information.

BR-7.5

Automation SHALL never duplicate Marketplace Orders.

---

# 8. FINANCIAL RULES

BR-8.1

Marketplace Cost SHALL be stored permanently.

BR-8.2

Marketplace Commission SHALL be included in Final Cost.

BR-8.3

Currency conversion SHALL use the configured exchange rate.

BR-8.4

Historical financial values SHALL never be recalculated.

BR-8.5

Customer Receives SHALL be stored permanently.

---

# 9. STATISTICS RULES

BR-9.1

Statistics SHALL update automatically.

BR-9.2

Only completed purchases SHALL affect financial statistics.

BR-9.3

Cancelled Orders SHALL NOT affect purchase statistics.

BR-9.4

Historical statistics SHALL remain available.

---

# 10. RECOVERY RULES

BR-10.1

Application restart SHALL NOT lose business data.

BR-10.2

PreOrders SHALL continue waiting.

BR-10.3

Purchasing Orders SHALL resume monitoring.

BR-10.4

Completed Orders SHALL remain unchanged.

BR-10.5

Recovery SHALL NOT create duplicate Marketplace Orders.

---

# 11. OPERATOR RULES

BR-11.1

The operator SHALL always be able to manually cancel a Client Order.

BR-11.2

The operator SHALL always be able to manually recreate a Marketplace Order.

BR-11.3

The operator SHALL always be able to modify system settings.

BR-11.4

The operator SHALL always receive important business notifications.

---

# 12. DATA INTEGRITY RULES

BR-12.1

Every business entity SHALL have a unique identifier.

BR-12.2

Foreign key relationships SHALL remain valid.

BR-12.3

Business history SHALL never become inconsistent.

BR-12.4

Completed Orders SHALL never be duplicated.

BR-12.5

Timeline SHALL preserve chronological order.

---

# 13. BUSINESS ACCEPTANCE

The business layer SHALL be considered complete when:

BR-13.1

All business rules are enforced.

BR-13.2

Business history remains consistent.

BR-13.3

Duplicate purchases are impossible.

BR-13.4

Financial information remains accurate.

BR-13.5

Automation follows all business rules.

---

End of BUSINESS_RULES.md