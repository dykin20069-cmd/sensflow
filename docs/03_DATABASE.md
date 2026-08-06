# DATABASE DESIGN

Document

DATABASE

Version

1.0

Status

Final Draft

---

# 1. PURPOSE

This document defines the logical database model of SensFlow Version 1.

The purpose of the database is to provide reliable, persistent storage for all business entities while maintaining data integrity and supporting future scalability.

The database SHALL be implemented using PostgreSQL.

This document describes logical entities and relationships only.

Physical implementation details are outside the scope of this document.

---

# 2. DATABASE PRINCIPLES

The database SHALL follow these principles.

DB-2.1

Every business entity SHALL have a unique identifier.

DB-2.2

Business history SHALL never be deleted.

DB-2.3

Completed Orders SHALL remain immutable.

DB-2.4

Foreign key relationships SHALL maintain referential integrity.

DB-2.5

Duplicate business entities SHALL be prevented.

DB-2.6

Business data SHALL survive unexpected application shutdown.

DB-2.7

Every timestamp SHALL be stored in UTC.

DB-2.8

Soft deletion SHALL be preferred over physical deletion.

---

# 3. DATABASE ENTITIES

Version 1 SHALL contain the following logical entities.

Customer

ClientOrder

MarketplaceOrder

SystemSettings

Statistics

Notification

TimelineEvent

SystemLog

These entities SHALL form the complete business model for Version 1.

---

# 4. ENTITY RELATIONSHIPS

Customer

↓

1 → N

↓

ClientOrder

↓

1 → N

↓

MarketplaceOrder

ClientOrder

↓

1 → N

↓

TimelineEvent

Customer

↓

1 → N

↓

ClientOrder

SystemSettings

↓

Application

Statistics

↓

Application

Notification

↓

ClientOrder

SystemLog

↓

Application

---

# 5. IDENTIFIERS

Every entity SHALL have its own internal UUID.

Internal UUIDs SHALL never change.

Business entities SHALL NOT use incremental numeric identifiers as primary keys.

External identifiers (such as Roblox User ID or RBXCreate Order ID) SHALL be stored separately from internal identifiers.

---

End of Chapter 1

# 6. CUSTOMER ENTITY

## 6.1 Purpose

The Customer entity stores persistent information about Roblox customers.

A Customer exists independently of Client Orders.

One Customer MAY have multiple Client Orders.

---

## 6.2 Fields

The Customer entity SHALL contain the following fields.

Internal UUID

Roblox User ID

Current Username

Username History

Current Place ID

Place ID History

Notes

Archived Flag

Created At

Updated At

Last Activity

---

## 6.3 Constraints

DB-6.3.1

Internal UUID SHALL be unique.

DB-6.3.2

Roblox User ID SHALL be unique.

DB-6.3.3

Current Username SHALL NOT be empty.

DB-6.3.4

Customer records SHALL never be physically deleted.

DB-6.3.5

Archived Customers SHALL remain available for searching.

---

# 7. CLIENT ORDER ENTITY

## 7.1 Purpose

The ClientOrder entity represents a business request created by the operator.

This is the primary business object of SensFlow.

---

## 7.2 Fields

Every ClientOrder SHALL contain:

Internal UUID

Customer UUID

Requested Robux

Customer Receives

Current Status

Current Place ID

Marketplace Rate Limit

Marketplace Cost

Marketplace Commission

Final Cost USD

Final Cost Local Currency

Created At

Updated At

Completed At

Cancelled At

---

## 7.3 Constraints

DB-7.3.1

Every ClientOrder SHALL belong to exactly one Customer.

DB-7.3.2

ClientOrder UUID SHALL be unique.

DB-7.3.3

Completed Orders SHALL become read-only.

DB-7.3.4

Cancelled Orders SHALL preserve complete history.

DB-7.3.5

Historical financial values SHALL never change after completion.

---

# 8. MARKETPLACE ORDER ENTITY

## 8.1 Purpose

MarketplaceOrder represents an individual RBXCreate order used to execute a ClientOrder.

One ClientOrder MAY create multiple MarketplaceOrders during its lifecycle.

---

## 8.2 Fields

MarketplaceOrder SHALL contain:

Internal UUID

ClientOrder UUID

RBXCreate Order ID

Marketplace Status

Purchase Rate

Requested Robux

Purchased Robux

Remaining Robux

Created At

Updated At

Completed At

Cancelled At

---

## 8.3 Constraints

DB-8.3.1

Marketplace Orders SHALL always belong to one ClientOrder.

DB-8.3.2

Only one MarketplaceOrder MAY be active for a ClientOrder at any moment.

DB-8.3.3

Historical MarketplaceOrders SHALL never be deleted.

---

# 9. TIMELINE EVENT ENTITY

## 9.1 Purpose

TimelineEvent stores the complete chronological history of every ClientOrder.

---

## 9.2 Event Types

Timeline SHALL support at minimum:

Client Order Created

Payment Confirmed

PreOrder Created

Purchasing Started

Marketplace Order Created

Marketplace Order Cancelled

Marketplace Order Completed

Automatic Reorder

Manual Reorder

Completed

Cancelled

---

## 9.3 Fields

TimelineEvent SHALL contain:

Internal UUID

ClientOrder UUID

Event Type

Description

Created At

---

## 9.4 Constraints

DB-9.4.1

Timeline events SHALL never be modified.

DB-9.4.2

Timeline events SHALL never be deleted.

DB-9.4.3

Timeline SHALL remain sorted chronologically.

---

End of Chapter 2

# 10. SYSTEM SETTINGS ENTITY

## 10.1 Purpose

The SystemSettings entity stores all configurable application parameters.

Settings SHALL persist between application restarts.

Only one active configuration SHALL exist at any time.

---

## 10.2 Fields

SystemSettings SHALL contain:

Internal UUID

Maximum Purchase Rate

Automatic Reorder Enabled

Automatic Reorder Interval

Marketplace Monitoring Interval

Marketplace Commission

USD Exchange Rate

Telegram Notifications Enabled

Application Timezone

Created At

Updated At

---

## 10.3 Constraints

DB-10.3.1

Only one active SystemSettings record SHALL exist.

DB-10.3.2

Configuration changes SHALL affect future operations only.

DB-10.3.3

Settings SHALL persist after restart.

---

# 11. NOTIFICATION ENTITY

## 11.1 Purpose

The Notification entity stores all Telegram notifications generated by SensFlow.

Notifications provide an auditable history of important business events.

---

## 11.2 Fields

Notification SHALL contain:

Internal UUID

ClientOrder UUID (optional)

Notification Type

Notification Title

Notification Message

Delivery Status

Created At

Delivered At

---

## 11.3 Constraints

DB-11.3.1

Notifications SHALL remain available for history.

DB-11.3.2

Delivery status SHALL be tracked.

DB-11.3.3

Failed deliveries SHALL remain stored.

---

# 12. SYSTEM LOG ENTITY

## 12.1 Purpose

SystemLog stores operational information useful for debugging and monitoring.

Business history SHALL NOT depend on SystemLog.

---

## 12.2 Fields

SystemLog SHALL contain:

Internal UUID

Log Level

Module

Message

Related Entity

Created At

---

## 12.3 Constraints

DB-12.3.1

Logs SHALL be append-only.

DB-12.3.2

Logs SHALL never modify business entities.

DB-12.3.3

Business operations SHALL continue even if log writing fails.

---

# 13. DATABASE RELATIONSHIPS

The logical relationships between entities SHALL be:

Customer

↓

1 → N

↓

ClientOrder

↓

1 → N

↓

MarketplaceOrder

ClientOrder

↓

1 → N

↓

TimelineEvent

ClientOrder

↓

1 → N

↓

Notification

SystemSettings

↓

Application

SystemLog

↓

Application

---

## 13.1 Relationship Constraints

DB-13.1.1

Every ClientOrder SHALL reference exactly one Customer.

DB-13.1.2

Every MarketplaceOrder SHALL reference exactly one ClientOrder.

DB-13.1.3

TimelineEvent SHALL always reference one ClientOrder.

DB-13.1.4

Notifications MAY reference a ClientOrder.

---

# 14. INDEXING STRATEGY

The database SHALL support efficient searching.

Indexes SHOULD exist for:

Customer Roblox User ID

Customer Username

ClientOrder Status

ClientOrder Created At

MarketplaceOrder Status

MarketplaceOrder RBXCreate Order ID

TimelineEvent ClientOrder

Notification Status

SystemLog Created At

---

# 15. DATA RETENTION

Business data SHALL be retained permanently unless explicitly removed by the operator.

The following entities SHALL never be automatically deleted:

Customer

ClientOrder

MarketplaceOrder

TimelineEvent

Statistics

Notification

SystemSettings

Automatic cleanup MAY be applied only to SystemLog in future versions.

---

# 16. BACKUP AND RECOVERY

The database SHALL support recovery after unexpected failures.

DB-16.1

Business entities SHALL remain consistent.

DB-16.2

Completed Orders SHALL remain unchanged.

DB-16.3

Recovery SHALL restore the latest committed database state.

DB-16.4

Application restart SHALL reconnect to the existing database automatically.

---

# 17. DATABASE ACCEPTANCE

The database SHALL be considered complete when:

DB-17.1

All required entities exist.

DB-17.2

All required relationships exist.

DB-17.3

All integrity constraints are enforced.

DB-17.4

Business history is preserved.

DB-17.5

Database survives application restart.

DB-17.6

No duplicate business entities can exist.

---

End of DATABASE.md