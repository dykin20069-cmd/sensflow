# TELEGRAM USER INTERFACE

Document

TELEGRAM_UI

Version

1.0

Status

Final Draft

---

# 1. PURPOSE

This document defines the Telegram interface for SensFlow Version 1.

Telegram is the primary operator interface.

All business operations SHALL be accessible through Telegram.

---

# 2. DESIGN PRINCIPLES

The Telegram interface SHALL follow these principles.

UI-2.1

Simple navigation.

UI-2.2

Minimum operator actions.

UI-2.3

No unnecessary confirmations.

UI-2.4

Consistent button placement.

UI-2.5

Business information before technical information.

UI-2.6

Fast access to active orders.

---

# 3. MAIN MENU

The Main Menu SHALL provide access to:

Create Order

Orders

Customers

Statistics

Settings

System Status

---

# 4. CREATE ORDER FLOW

Creating an order SHALL require the following information:

Roblox Username

Requested Robux

Place ID

The system SHALL automatically attempt to find the Place ID.

If automatic discovery fails, the operator SHALL be able to enter the Place ID manually.

---

# 5. ORDER LIST

Orders SHALL be grouped by status.

Available sections:

Draft

PreOrder

Purchasing

Completed

Cancelled

Each section SHALL display the number of orders it contains.

---

# 6. ORDER DETAILS

The Order Details screen SHALL display:

Customer Username

Current Status

Requested Robux

Customer Receives

Current Place ID

Maximum Purchase Rate

Marketplace Cost

Final Cost

Timeline

Creation Date

Completion Date

---

# 7. ORDER ACTIONS

Available actions SHALL include:

Confirm Payment

Manual Reorder

Cancel Order

Refresh Information

View Timeline

---

# 8. CUSTOMER SCREEN

Customer Details SHALL display:

Username

Roblox User ID

Current Place ID

Previous Usernames

Previous Place IDs

Order History

Notes

---

# 9. STATISTICS SCREEN

Statistics SHALL display:

Completed Orders

PreOrders

Purchasing Orders

Purchased Robux

Average Purchase Rate

Marketplace Commission Paid

Total Spending

---

# 10. SETTINGS SCREEN

The Settings screen SHALL allow changing:

Maximum Purchase Rate

Marketplace Commission

USD Exchange Rate

Automatic Reorder

Automatic Reorder Interval

Marketplace Monitoring Interval

Telegram Notifications

Timezone

---

# 11. NOTIFICATIONS

Telegram SHALL notify the operator about:

Completed purchases

Marketplace errors

Application restart

Automatic recovery

Order cancellation

Synchronization failures

---

# 12. NAVIGATION

The interface SHALL support:

Back

Home

Refresh

Close

These actions SHALL remain consistent across all screens.

---

# 13. UI ACCEPTANCE

The Telegram interface SHALL be considered complete when:

UI-13.1

Every business operation is accessible.

UI-13.2

Navigation is consistent.

UI-13.3

Business information is displayed correctly.

UI-13.4

Notifications are delivered successfully.

UI-13.5

The operator can manage the entire purchasing workflow without leaving Telegram.

---

End of TELEGRAM_UI.md