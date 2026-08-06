# SOFTWARE REQUIREMENTS SPECIFICATION

Document

PROJECT_REQUIREMENTS

Version

1.0

Status

Final Draft

---

# 1. SYSTEM OVERVIEW

## 1.1 Purpose

This document defines the complete functional and non-functional requirements for SensFlow Version 1.

It is the primary specification used during implementation.

All project modules, services, algorithms, database models and user interfaces SHALL comply with this document.

If any implementation contradicts this specification, the implementation MUST be considered incorrect unless BUSINESS_RULES explicitly overrides the requirement.

---

## 1.2 Product Definition

SensFlow is a Telegram-first automation platform designed to automate Robux purchasing through the RBXCreate Marketplace.

SensFlow is NOT a marketplace.

RBXCreate remains responsible for marketplace operations.

SensFlow is responsible for:

- customer management;
- business logic;
- order lifecycle management;
- automation;
- scheduling;
- financial calculations;
- statistics;
- recovery;
- notifications.

---

## 1.3 Target Users

Version 1 targets a single operator managing Robux purchases for customers.

Multi-operator support is outside the scope of Version 1.

---

## 1.4 Primary Goals

The system SHALL satisfy the following goals.

REQ-1.4.1

Reduce repetitive manual work.

REQ-1.4.2

Reduce customer waiting time.

REQ-1.4.3

Increase completed customer orders per Marketplace stock opportunity.

REQ-1.4.4

Prevent duplicate Marketplace Orders.

REQ-1.4.5

Provide complete operational visibility.

REQ-1.4.6

Maintain complete historical records.

REQ-1.4.7

Automatically recover after failures.

REQ-1.4.8

Allow operators to manage the entire workflow from Telegram.

---

## 1.5 Version Scope

Version 1 SHALL include the following functional domains.

REQ-1.5.1

Customer Management.

REQ-1.5.2

Draft Orders.

REQ-1.5.3

PreOrders.

REQ-1.5.4

Active Orders.

REQ-1.5.5

Completed Orders.

REQ-1.5.6

Marketplace Integration.

REQ-1.5.7

Marketplace Synchronization.

REQ-1.5.8

Stock Monitoring.

REQ-1.5.9

Stock Cache.

REQ-1.5.10

Order Scheduler.

REQ-1.5.11

Reorder Engine.

REQ-1.5.12

Timeline.

REQ-1.5.13

Financial Calculations.

REQ-1.5.14

Statistics.

REQ-1.5.15

Telegram Interface.

REQ-1.5.16

Notifications.

REQ-1.5.17

Recovery.

REQ-1.5.18

Logging.

REQ-1.5.19

Settings.

REQ-1.5.20

Docker Deployment.

REQ-1.5.21

PostgreSQL Database.

---

## 1.6 Version Exclusions

The following features SHALL NOT be implemented in Version 1.

REQ-1.6.1

Multiple Marketplace support.

REQ-1.6.2

Multiple Operators.

REQ-1.6.3

Role-Based Access Control.

REQ-1.6.4

Customer Billing.

REQ-1.6.5

Customer Web Portal.

REQ-1.6.6

Public REST API.

REQ-1.6.7

Artificial Intelligence decision making.

REQ-1.6.8

Automatic currency exchange synchronization.

REQ-1.6.9

Supplier analytics.

REQ-1.6.10

Cloud synchronization.

---

## 1.7 Product Principles

Every implementation SHALL follow these principles.

REQ-1.7.1

Automation First.

REQ-1.7.2

Manual Override Must Always Be Available.

REQ-1.7.3

Business Safety Has Higher Priority Than Speed.

REQ-1.7.4

Single Source of Truth.

REQ-1.7.5

Immutable History.

REQ-1.7.6

Deterministic Behaviour.

REQ-1.7.7

Recoverability.

REQ-1.7.8

Modularity.

REQ-1.7.9

Observability.

---

## 1.8 Expected Operator Workflow

The standard workflow SHALL be:

Customer Request

↓

Draft Order

↓

Payment Confirmation

↓

PreOrder

↓

Marketplace Stock Detected

↓

Scheduler

↓

Marketplace Order

↓

Automatic Monitoring

↓

Automatic Reorder (if required)

↓

Marketplace Purchase Completed

↓

Financial Calculation

↓

Telegram Notification

↓

Completed Order

↓

Permanent History

---

## 1.9 System Responsibilities

SensFlow SHALL be responsible for:

REQ-1.9.1

Managing Customers.

REQ-1.9.2

Managing Client Orders.

REQ-1.9.3

Managing Marketplace Orders.

REQ-1.9.4

Monitoring Marketplace stock.

REQ-1.9.5

Selecting optimal purchase strategy.

REQ-1.9.6

Automatically recreating Marketplace Orders.

REQ-1.9.7

Calculating financial values.

REQ-1.9.8

Maintaining statistics.

REQ-1.9.9

Maintaining complete history.

REQ-1.9.10

Recovering automatically after restart.

---

## 1.10 Non-Functional Requirements

NFR-1.10.1

The system SHALL be fully deployable using Docker Compose.

NFR-1.10.2

The system SHALL continue operating after unexpected application restart.

NFR-1.10.3

Historical business data SHALL never be lost.

NFR-1.10.4

Business operations SHALL be deterministic.

NFR-1.10.5

The architecture SHALL support future expansion without major redesign.

---

## 1.11 Acceptance Criteria

Version 1 SHALL be considered complete only if:

REQ-1.11.1

All mandatory functional requirements are implemented.

REQ-1.11.2

All mandatory non-functional requirements are satisfied.

REQ-1.11.3

All mandatory modules operate correctly.

REQ-1.11.4

Business Rules are not violated.

REQ-1.11.5

All required tests pass successfully.

REQ-1.11.6

Marketplace synchronization is stable.

REQ-1.11.7

Automatic recovery works correctly.

REQ-1.11.8

No duplicate Marketplace Orders can exist.

REQ-1.11.9

Financial calculations are correct.

REQ-1.11.10

The operator can complete the entire purchasing workflow using Telegram only.

---

End of Chapter 1

# 2. CUSTOMER DOMAIN

## 2.1 Purpose

The Customer Domain manages the identity, history and persistent information of Roblox customers.

Customers are long-lived business entities and exist independently from orders.

Every Client Order SHALL belong to exactly one Customer.

---

## 2.2 Definitions

Customer

A Roblox user for whom Robux may be purchased.

Current Username

The latest known Roblox username.

Username History

All previously known usernames.

Current Place ID

The Place ID currently used when creating Marketplace Orders.

Place ID History

Historical list of previously used Place IDs.

Roblox User ID

Permanent Roblox identifier.

Internal Customer ID

Internal UUID generated by SensFlow.

---

## 2.3 Business Requirements

REQ-2.3.1

Every Customer SHALL have exactly one Internal Customer ID.

REQ-2.3.2

Every Customer SHALL have exactly one Roblox User ID.

REQ-2.3.3

Every Customer SHALL have one Current Username.

REQ-2.3.4

Every Customer MAY have multiple historical usernames.

REQ-2.3.5

Every Customer SHALL have one Current Place ID.

REQ-2.3.6

Every Customer MAY have multiple historical Place IDs.

REQ-2.3.7

Customers SHALL exist independently of Client Orders.

REQ-2.3.8

Deleting Customers is prohibited.

REQ-2.3.9

Archiving Customers is allowed.

REQ-2.3.10

Archived Customers retain complete history.

---

## 2.4 Business Rules

REQ-2.4.1

Customer uniqueness SHALL be determined by Roblox User ID.

REQ-2.4.2

If Roblox User ID is unavailable, Customer creation SHALL fail.

REQ-2.4.3

Username changes SHALL update Current Username.

REQ-2.4.4

Previous usernames SHALL automatically move into Username History.

REQ-2.4.5

Changing Current Place ID SHALL automatically move the previous value into Place ID History.

REQ-2.4.6

Customer history SHALL never be deleted.

---

## 2.5 User Workflow

Operator enters Roblox Username

↓

System requests Roblox User ID

↓

Customer found?

↓

Yes

↓

Load Customer

↓

Load Current Place ID

↓

Continue

↓

No

↓

Create Customer

↓

Store Roblox User ID

↓

Store Username

↓

Search Place ID

↓

Customer Created

---

## 2.6 Edge Cases

REQ-2.6.1

Duplicate usernames SHALL NOT create duplicate Customers.

REQ-2.6.2

Username changes SHALL preserve Customer identity.

REQ-2.6.3

Manual Place ID replacement SHALL preserve previous values.

REQ-2.6.4

Failed Roblox API requests SHALL NOT create Customers.

---

## 2.7 Database Requirements

Each Customer SHALL store:

Internal UUID

Roblox User ID

Current Username

Username History

Current Place ID

Place ID History

Creation Timestamp

Last Activity Timestamp

Archived Flag

Notes

Statistics

---

## 2.8 Telegram Behaviour

Telegram SHALL allow the operator to:

View Customer

Search Customer

View Username History

View Place ID History

Refresh Customer Information

Archive Customer

Customer creation SHALL remain automatic.

---

## 2.9 Acceptance Criteria

REQ-2.9.1

Customer identity remains stable after username changes.

REQ-2.9.2

Customer history is preserved.

REQ-2.9.3

Duplicate Customers cannot exist.

REQ-2.9.4

Automatic Customer creation works correctly.

REQ-2.9.5

Customer information survives system restart.

---

End of Chapter 2


# 3. ORDER DOMAIN

## 3.1 Purpose

The Order Domain manages the complete lifecycle of every customer purchase.

A Client Order represents one business request to purchase Robux for one Customer.

Client Orders are the primary business entity of SensFlow.

Marketplace Orders are implementation details and are created only to fulfill a Client Order.

---

## 3.2 Definitions

Client Order

A business order created by the operator.

Marketplace Order

A temporary marketplace request created on RBXCreate.

Requested Robux

The amount of Robux requested by the customer.

Customer Receives

The amount of Robux the customer will actually receive after Roblox tax.

Marketplace Rate

Current purchase rate on RBXCreate.

Marketplace Cost

Actual purchase price paid on RBXCreate.

Marketplace Commission

RBXCreate execution commission.

Final Cost

Marketplace Cost including commission.

Timeline

Complete chronological history of the Client Order.

---

## 3.3 Client Order Lifecycle

Every Client Order SHALL always be in exactly one state.

The allowed states are:

Draft

↓

PreOrder

↓

Purchasing

↓

Completed

A Client Order MAY also transition to:

Cancelled

The state machine SHALL prohibit invalid transitions.

---

## 3.4 Draft Orders

Draft Orders represent unpaid or unconfirmed customer requests.

REQ-3.4.1

Draft Orders SHALL NOT communicate with RBXCreate.

REQ-3.4.2

Draft Orders SHALL remain editable.

REQ-3.4.3

Draft Orders MAY be deleted.

REQ-3.4.4

Draft Orders SHALL store all customer information.

REQ-3.4.5

Draft Orders SHALL contain the requested Robux amount.

REQ-3.4.6

Draft Orders SHALL contain the Customer reference.

REQ-3.4.7

Draft Orders SHALL contain the Place ID.

---

## 3.5 Payment Confirmation

When payment is confirmed:

If marketplace stock is available

↓

Client Order SHALL transition directly to Purchasing.

If marketplace stock is unavailable

↓

Client Order SHALL transition to PreOrder.

The operator SHALL NOT manually choose between Purchasing and PreOrder.

The decision MUST be automatic.

---

## 3.6 PreOrders

PreOrders represent paid customer orders waiting for suitable marketplace stock.

REQ-3.6.1

PreOrders SHALL participate in Stock Monitoring.

REQ-3.6.2

PreOrders SHALL participate in Scheduler execution.

REQ-3.6.3

PreOrders SHALL NOT have an active Marketplace Order while no suitable stock exists.

REQ-3.6.4

When suitable stock appears, Scheduler SHALL determine whether the order should be executed.

REQ-3.6.5

Selected PreOrders SHALL automatically transition to Purchasing.

---

## 3.7 Purchasing Orders

Purchasing Orders represent orders currently being executed through RBXCreate.

REQ-3.7.1

Purchasing Orders SHALL always have exactly one active Marketplace Order.

REQ-3.7.2

Marketplace Orders MAY be recreated multiple times.

REQ-3.7.3

Client Order identity SHALL remain unchanged.

REQ-3.7.4

Automatic Reorder MAY replace Marketplace Orders without changing Client Order status.

REQ-3.7.5

Manual Reorder SHALL use the same logic as Automatic Reorder.

---

## 3.8 Completed Orders

Completed Orders represent successfully purchased Robux.

REQ-3.8.1

Completed Orders SHALL become read-only.

REQ-3.8.2

Financial calculations SHALL be finalized.

REQ-3.8.3

Completion notification SHALL be sent.

REQ-3.8.4

Statistics SHALL be updated.

REQ-3.8.5

Timeline SHALL receive completion event.

---

## 3.9 Cancelled Orders

Cancelled Orders represent orders manually cancelled by the operator.

REQ-3.9.1

Cancelled Orders SHALL preserve complete history.

REQ-3.9.2

Cancelled Orders SHALL NOT participate in Scheduler.

REQ-3.9.3

Cancelled Orders SHALL NOT create Marketplace Orders.

---

## 3.10 Acceptance Criteria

REQ-3.10.1

Every Client Order has exactly one state.

REQ-3.10.2

Invalid state transitions are impossible.

REQ-3.10.3

Payment automatically determines Purchasing or PreOrder.

REQ-3.10.4

Completed Orders become immutable.

REQ-3.10.5

Cancelled Orders preserve complete history.

---

End of Part A

## 3.11 Marketplace Orders

A Marketplace Order is a temporary order created on RBXCreate for executing one Client Order.

Marketplace Orders are implementation objects and SHALL NOT exist independently.

One Client Order MAY create multiple Marketplace Orders during its lifecycle.

Only one Marketplace Order MAY be active at any given time.

---

## 3.12 Marketplace Order Creation

REQ-3.12.1

Marketplace Orders SHALL only be created for Purchasing Orders.

REQ-3.12.2

Marketplace Orders SHALL never be created for Draft Orders.

REQ-3.12.3

Marketplace Orders SHALL never be created for Cancelled Orders.

REQ-3.12.4

Marketplace Orders SHALL use the Customer's current Place ID.

REQ-3.12.5

Marketplace Orders SHALL use the requested Robux amount from the Client Order.

REQ-3.12.6

The maximum purchase rate SHALL be taken from system settings.

---

## 3.13 Marketplace Order Monitoring

Every active Marketplace Order SHALL be monitored automatically.

Monitoring SHALL periodically check:

- current status;
- purchased amount;
- remaining amount;
- execution result;
- cancellation status.

The monitoring interval SHALL be configurable in system settings.

---

## 3.14 Automatic Reorder

Automatic Reorder is responsible for maintaining the highest possible execution priority.

REQ-3.14.1

If automatic reorder is enabled, the system SHALL periodically evaluate every Purchasing Order.

REQ-3.14.2

The system MAY cancel the current Marketplace Order and immediately create a new Marketplace Order.

REQ-3.14.3

Automatic Reorder SHALL never change the Client Order.

REQ-3.14.4

Only the Marketplace Order may be recreated.

REQ-3.14.5

The operator SHALL be able to disable Automatic Reorder globally.

---

## 3.15 Manual Reorder

The operator SHALL always be able to manually recreate the Marketplace Order.

REQ-3.15.1

Manual Reorder SHALL immediately cancel the active Marketplace Order.

REQ-3.15.2

After successful cancellation, a new Marketplace Order SHALL be created automatically.

REQ-3.15.3

Manual Reorder SHALL preserve the Client Order.

REQ-3.15.4

Manual Reorder SHALL create an event in the Timeline.

---

## 3.16 Successful Purchase

A purchase SHALL be considered completed only after RBXCreate confirms successful execution.

REQ-3.16.1

Completed purchases SHALL immediately transition the Client Order to Completed.

REQ-3.16.2

Marketplace monitoring SHALL stop.

REQ-3.16.3

Financial calculations SHALL be finalized.

REQ-3.16.4

Statistics SHALL be updated.

REQ-3.16.5

A Telegram notification SHALL be sent.

---

## 3.17 Timeline

Every Client Order SHALL maintain a complete chronological history.

Timeline events SHALL include:

- Order Created
- Payment Confirmed
- PreOrder Created
- Purchasing Started
- Marketplace Order Created
- Marketplace Order Cancelled
- Marketplace Order Completed
- Manual Reorder
- Automatic Reorder
- Order Completed
- Order Cancelled

Timeline records SHALL never be deleted.

---

## 3.18 Acceptance Criteria

REQ-3.18.1

Marketplace Orders are created only for Purchasing Orders.

REQ-3.18.2

Only one Marketplace Order may be active simultaneously.

REQ-3.18.3

Automatic Reorder never changes the Client Order.

REQ-3.18.4

Manual Reorder behaves identically to Automatic Reorder.

REQ-3.18.5

Completed purchases correctly finalize the Client Order.

REQ-3.18.6

Timeline preserves the complete order history.

---

End of Chapter 3

# 4. MARKETPLACE DOMAIN

## 4.1 Purpose

The Marketplace Domain is responsible for interacting with RBXCreate.

Its responsibilities include:

- monitoring marketplace stock;
- creating Marketplace Orders;
- cancelling Marketplace Orders;
- tracking execution status;
- synchronizing Marketplace Orders;
- selecting eligible Client Orders for execution.

Business logic SHALL remain inside SensFlow.

RBXCreate SHALL be treated only as an external marketplace.

---

## 4.2 Stock Definition

Marketplace Stock represents the amount of Robux currently available for purchase at or below the configured maximum purchase rate.

Only stock satisfying the configured rate limit SHALL be considered eligible.

---

## 4.3 Maximum Purchase Rate

REQ-4.3.1

The operator SHALL configure the maximum acceptable purchase rate.

REQ-4.3.2

Only Marketplace stock with a rate less than or equal to the configured limit SHALL be considered.

REQ-4.3.3

Stock above the configured limit SHALL be ignored.

REQ-4.3.4

Changing the maximum purchase rate SHALL immediately affect future purchases.

---

## 4.4 Stock Monitoring

SensFlow SHALL continuously monitor Marketplace stock.

REQ-4.4.1

Monitoring SHALL operate automatically.

REQ-4.4.2

The monitoring interval SHALL be configurable.

REQ-4.4.3

Monitoring SHALL continue while the application is running.

REQ-4.4.4

Monitoring SHALL automatically resume after restart.

---

## 4.5 Stock Detection

Whenever eligible Marketplace stock appears, SensFlow SHALL immediately evaluate waiting Client Orders.

Eligible stock MUST satisfy:

- Marketplace Rate ≤ Maximum Purchase Rate
- Available Robux > 0

Only then SHALL Scheduler begin order allocation.

---

## 4.6 Scheduler

The Scheduler determines which Client Orders receive available Marketplace stock.

REQ-4.6.1

Only PreOrders SHALL participate in scheduling.

REQ-4.6.2

Draft Orders SHALL NOT participate.

REQ-4.6.3

Completed Orders SHALL NOT participate.

REQ-4.6.4

Cancelled Orders SHALL NOT participate.

---

## 4.7 Scheduling Strategy

Version 1 SHALL implement one scheduling strategy.

Strategy Name:

Maximum Customers

The Scheduler SHALL prioritize completing the largest possible number of customers using currently available Marketplace stock.

Example:

Available Stock:

1000 Robux

Waiting Orders:

229

231

514

950

The Scheduler SHOULD prefer:

229

231

514

instead of:

950

because more customers will be completed.

---

## 4.8 Purchasing Transition

Selected PreOrders SHALL automatically transition to Purchasing.

Marketplace Orders SHALL then be created automatically.

Orders not selected SHALL remain in PreOrder status.

---

## 4.9 Synchronization

SensFlow SHALL periodically synchronize Marketplace Orders with RBXCreate.

Synchronization SHALL detect:

- completed purchases;
- cancelled Marketplace Orders;
- remaining quantity;
- execution status.

Synchronization SHALL update Client Orders accordingly.

---

## 4.10 Failure Handling

If Marketplace communication fails:

REQ-4.10.1

The system SHALL retry automatically.

REQ-4.10.2

Existing Client Orders SHALL remain unchanged.

REQ-4.10.3

Marketplace synchronization SHALL resume when connectivity returns.

REQ-4.10.4

All failures SHALL be logged.

---

## 4.11 Acceptance Criteria

REQ-4.11.1

Marketplace stock is monitored continuously.

REQ-4.11.2

Only eligible stock is considered.

REQ-4.11.3

Scheduler correctly selects Client Orders.

REQ-4.11.4

Purchasing starts automatically after stock appears.

REQ-4.11.5

Marketplace synchronization remains stable.

REQ-4.11.6

Communication failures do not lose business data.

---

End of Chapter 4

# 5. AUTOMATION DOMAIN

## 5.1 Purpose

The Automation Domain is responsible for reducing manual operator actions while maintaining complete control over the purchasing process.

Automation SHALL never modify business data incorrectly.

Every automated action MUST produce the same result as if it had been performed manually by the operator.

---

## 5.2 Automatic Reorder

Automatic Reorder is responsible for maintaining the highest possible Marketplace execution priority.

REQ-5.2.1

Automatic Reorder SHALL only operate on Purchasing Orders.

REQ-5.2.2

PreOrders SHALL NOT be reordered.

REQ-5.2.3

Draft Orders SHALL NOT be reordered.

REQ-5.2.4

Completed Orders SHALL NOT be reordered.

REQ-5.2.5

Cancelled Orders SHALL NOT be reordered.

---

## 5.3 Automatic Reorder Process

When Automatic Reorder executes:

1. Check Marketplace Order status.

2. If the order has already been completed, stop processing.

3. If the order is still active, cancel it.

4. Wait for successful cancellation confirmation.

5. Create a new Marketplace Order.

6. Continue monitoring.

The Client Order SHALL remain unchanged during the entire process.

---

## 5.4 Manual Reorder

The operator SHALL always be able to manually recreate a Marketplace Order.

REQ-5.4.1

Manual Reorder SHALL use exactly the same workflow as Automatic Reorder.

REQ-5.4.2

Manual Reorder SHALL immediately start execution.

REQ-5.4.3

Manual Reorder SHALL create a Timeline event.

REQ-5.4.4

Manual Reorder SHALL never duplicate Client Orders.

---

## 5.5 Reorder Interval

Automatic Reorder SHALL execute periodically.

REQ-5.5.1

The interval SHALL be configurable.

REQ-5.5.2

Changing the interval SHALL take effect without restarting the application.

REQ-5.5.3

The interval SHALL apply globally to all Purchasing Orders.

---

## 5.6 Stock Reaction

Whenever suitable Marketplace stock appears:

REQ-5.6.1

Scheduler SHALL immediately evaluate waiting PreOrders.

REQ-5.6.2

Selected Client Orders SHALL transition to Purchasing.

REQ-5.6.3

Marketplace Orders SHALL be created automatically.

REQ-5.6.4

Remaining Client Orders SHALL continue waiting.

---

## 5.7 Completion Detection

Automation SHALL continuously monitor Marketplace execution.

REQ-5.7.1

Completed purchases SHALL immediately stop Automatic Reorder.

REQ-5.7.2

Completed purchases SHALL finalize the Client Order.

REQ-5.7.3

Completed purchases SHALL generate a Telegram notification.

REQ-5.7.4

Completed purchases SHALL update Statistics automatically.

---

## 5.8 Safety Requirements

Automation SHALL never create duplicate Marketplace Orders.

REQ-5.8.1

Only one active Marketplace Order MAY exist for a Client Order.

REQ-5.8.2

Automatic Reorder SHALL wait for Marketplace cancellation before creating a replacement order.

REQ-5.8.3

Unexpected API errors SHALL NOT modify Client Order state.

REQ-5.8.4

Every automation action SHALL be logged.

---

## 5.9 Recovery

After application restart:

REQ-5.9.1

Automation SHALL resume automatically.

REQ-5.9.2

Purchasing Orders SHALL continue monitoring.

REQ-5.9.3

PreOrders SHALL immediately participate in stock monitoring.

REQ-5.9.4

Completed Orders SHALL remain unchanged.

---

## 5.10 Acceptance Criteria

REQ-5.10.1

Automatic Reorder operates correctly.

REQ-5.10.2

Manual Reorder behaves identically.

REQ-5.10.3

Completed purchases stop automation.

REQ-5.10.4

Duplicate Marketplace Orders cannot occur.

REQ-5.10.5

Automation resumes correctly after restart.

---

End of Chapter 5

# 6. TELEGRAM INTERFACE

## 6.1 Purpose

Telegram SHALL be the primary user interface for SensFlow Version 1.

The operator SHALL be able to perform every business operation without accessing the RBXCreate website.

---

## 6.2 Main Menu

The system SHALL provide a main menu.

REQ-6.2.1

The Main Menu SHALL provide access to all major system functions.

REQ-6.2.2

Navigation SHALL require no text commands.

REQ-6.2.3

The interface SHALL primarily use Telegram inline buttons.

---

## 6.3 Client Order Management

The operator SHALL be able to:

REQ-6.3.1

Create a Client Order.

REQ-6.3.2

View Client Orders.

REQ-6.3.3

Search Client Orders.

REQ-6.3.4

Cancel Client Orders.

REQ-6.3.5

Open Client Order details.

REQ-6.3.6

Manually recreate Marketplace Orders.

---

## 6.4 Customer Management

The operator SHALL be able to:

REQ-6.4.1

Search Customers.

REQ-6.4.2

View Customer information.

REQ-6.4.3

Refresh Customer information.

REQ-6.4.4

Update Place ID manually.

---

## 6.5 Order Lists

The interface SHALL allow viewing orders grouped by status.

REQ-6.5.1

Draft Orders.

REQ-6.5.2

PreOrders.

REQ-6.5.3

Purchasing Orders.

REQ-6.5.4

Completed Orders.

REQ-6.5.5

Cancelled Orders.

---

## 6.6 Notifications

The system SHALL notify the operator about important events.

Notifications SHALL include:

- successful purchase;
- Marketplace errors;
- failed synchronization;
- application recovery;
- automatic reorder events;
- manual reorder events.

---

## 6.7 Settings

The operator SHALL be able to modify system settings through Telegram.

REQ-6.7.1

Maximum purchase rate.

REQ-6.7.2

Automatic reorder interval.

REQ-6.7.3

Exchange rate.

REQ-6.7.4

Automation settings.

---

## 6.8 Statistics

The operator SHALL be able to view business statistics.

Statistics SHALL include:

- completed orders;
- active orders;
- waiting orders;
- purchased Robux;
- purchase costs;
- average purchase rate.

---

## 6.9 Acceptance Criteria

REQ-6.9.1

Every business operation can be completed through Telegram.

REQ-6.9.2

The operator never needs to manually access RBXCreate during normal operation.

REQ-6.9.3

Telegram navigation remains simple and consistent.

REQ-6.9.4

All important events generate notifications.

---

End of Chapter 6

# 7. FINANCIAL REQUIREMENTS

## 7.1 Purpose

The Financial Domain is responsible for calculating and storing all business-related financial information associated with Client Orders.

Financial calculations SHALL be performed automatically.

---

## 7.2 Marketplace Cost

REQ-7.2.1

The system SHALL record the Marketplace purchase rate for every completed Client Order.

REQ-7.2.2

The system SHALL record the purchased Robux amount.

REQ-7.2.3

The Marketplace purchase cost SHALL be stored permanently.

---

## 7.3 Marketplace Commission

REQ-7.3.1

The Marketplace execution commission SHALL be configurable.

REQ-7.3.2

The commission SHALL be included when calculating the Final Cost.

REQ-7.3.3

The commission SHALL NOT modify the Marketplace purchase rate.

REQ-7.3.4

The Final Cost SHALL include Marketplace Cost plus Marketplace Commission.

---

## 7.4 Currency Conversion

REQ-7.4.1

The operator SHALL configure the USD to local currency exchange rate.

REQ-7.4.2

The exchange rate SHALL be applied to every completed purchase.

REQ-7.4.3

Changing the exchange rate SHALL affect future calculations only.

REQ-7.4.4

Historical orders SHALL preserve the exchange rate used at the time of completion.

---

## 7.5 Customer Receives

REQ-7.5.1

The system SHALL calculate the amount of Robux received by the customer.

REQ-7.5.2

Customer Receives SHALL be stored permanently.

REQ-7.5.3

The calculation SHALL follow Roblox marketplace rules.

---

## 7.6 Completed Order Summary

Every completed Client Order SHALL include:

- Requested Robux;
- Customer Receives;
- Marketplace Rate;
- Marketplace Cost;
- Marketplace Commission;
- Final Cost (USD);
- Final Cost (Local Currency).

---

## 7.7 Acceptance Criteria

REQ-7.7.1

Every completed purchase contains complete financial information.

REQ-7.7.2

Marketplace commission is included correctly.

REQ-7.7.3

Currency conversion is calculated correctly.

REQ-7.7.4

Historical financial records remain unchanged.

---

End of Chapter 7

# 8. STATISTICS REQUIREMENTS

## 8.1 Purpose

The Statistics Domain provides operational and business insights about SensFlow activity.

Statistics SHALL be generated automatically.

---

## 8.2 Order Statistics

REQ-8.2.1

The system SHALL track the total number of Client Orders.

REQ-8.2.2

The system SHALL track Draft Orders.

REQ-8.2.3

The system SHALL track PreOrders.

REQ-8.2.4

The system SHALL track Purchasing Orders.

REQ-8.2.5

The system SHALL track Completed Orders.

REQ-8.2.6

The system SHALL track Cancelled Orders.

---

## 8.3 Purchase Statistics

REQ-8.3.1

The system SHALL calculate the total purchased Robux.

REQ-8.3.2

The system SHALL calculate the total amount paid.

REQ-8.3.3

The system SHALL calculate the average Marketplace Rate.

REQ-8.3.4

The system SHALL calculate the average purchase cost.

REQ-8.3.5

The system SHALL calculate the total Marketplace Commission paid.

---

## 8.4 Daily Statistics

REQ-8.4.1

The system SHALL generate daily statistics.

REQ-8.4.2

The system SHALL generate weekly statistics.

REQ-8.4.3

The system SHALL generate monthly statistics.

---

## 8.5 Acceptance Criteria

REQ-8.5.1

Statistics update automatically.

REQ-8.5.2

Completed purchases are reflected correctly.

REQ-8.5.3

Historical statistics remain available.

---

End of Chapter 8

# 9. RECOVERY AND LOGGING

## 9.1 Purpose

The Recovery and Logging Domain ensures operational stability and preserves complete business history.

---

## 9.2 Recovery

REQ-9.2.1

The system SHALL automatically recover after restart.

REQ-9.2.2

PreOrders SHALL continue waiting.

REQ-9.2.3

Purchasing Orders SHALL resume monitoring.

REQ-9.2.4

Completed Orders SHALL remain unchanged.

REQ-9.2.5

Cancelled Orders SHALL remain unchanged.

---

## 9.3 Logging

REQ-9.3.1

The system SHALL log every important business event.

REQ-9.3.2

Marketplace communication SHALL be logged.

REQ-9.3.3

Order state changes SHALL be logged.

REQ-9.3.4

Automation events SHALL be logged.

REQ-9.3.5

System errors SHALL be logged.

---

## 9.4 Acceptance Criteria

REQ-9.4.1

Recovery restores business operations.

REQ-9.4.2

Business data is never lost.

REQ-9.4.3

Logs contain complete operational history.

---

End of Chapter 9

# 10. SYSTEM SETTINGS

## 10.1 Purpose

System Settings allow the operator to configure SensFlow without modifying application code.

---

## 10.2 Marketplace Settings

REQ-10.2.1

The operator SHALL configure the Maximum Purchase Rate.

REQ-10.2.2

The operator SHALL enable or disable Automatic Reorder.

REQ-10.2.3

The operator SHALL configure the Automatic Reorder interval.

---

## 10.3 Financial Settings

REQ-10.3.1

The operator SHALL configure Marketplace Commission.

REQ-10.3.2

The operator SHALL configure the USD exchange rate.

---

## 10.4 Notification Settings

REQ-10.4.1

The operator SHALL enable or disable Telegram notifications.

REQ-10.4.2

The operator SHALL configure notification categories.

---

## 10.5 System Settings

REQ-10.5.1

The operator SHALL configure stock monitoring interval.

REQ-10.5.2

The operator SHALL configure synchronization interval.

REQ-10.5.3

The operator SHALL configure application timezone.

---

## 10.6 Acceptance Criteria

REQ-10.6.1

Setting changes are applied successfully.

REQ-10.6.2

New settings affect future operations only.

REQ-10.6.3

Settings persist after restart.

---

End of Chapter 10

# 11. SECURITY REQUIREMENTS

## 11.1 Purpose

The Security Domain protects business operations, application configuration and Marketplace credentials.

Version 1 is intended for a single trusted operator.

---

## 11.2 Authentication

REQ-11.2.1

The system SHALL require Telegram authorization before allowing access.

REQ-11.2.2

Only authorized Telegram users SHALL be able to access the application.

REQ-11.2.3

Unauthorized users SHALL be denied access.

---

## 11.3 API Credentials

REQ-11.3.1

Marketplace API credentials SHALL be stored securely.

REQ-11.3.2

API credentials SHALL never appear in logs.

REQ-11.3.3

API credentials SHALL never be exposed through Telegram.

REQ-11.3.4

Changing API credentials SHALL not require application reinstallation.

---

## 11.4 Business Protection

REQ-11.4.1

Completed Orders SHALL NOT be modified.

REQ-11.4.2

Financial history SHALL NOT be modified.

REQ-11.4.3

Order history SHALL remain permanently available.

REQ-11.4.4

Business data SHALL survive unexpected application termination.

---

## 11.5 Acceptance Criteria

REQ-11.5.1

Unauthorized access is impossible.

REQ-11.5.2

Marketplace credentials remain protected.

REQ-11.5.3

Business history remains intact.

REQ-11.5.4

Sensitive information never appears in logs.

---

End of Chapter 11

# 12. FINAL SYSTEM ACCEPTANCE

## 12.1 Purpose

This chapter defines the conditions under which SensFlow Version 1 is considered complete.

---

## 12.2 Functional Acceptance

REQ-12.2.1

Customer Management operates correctly.

REQ-12.2.2

Client Orders operate correctly.

REQ-12.2.3

Marketplace synchronization operates correctly.

REQ-12.2.4

Automatic Reorder operates correctly.

REQ-12.2.5

Manual Reorder operates correctly.

REQ-12.2.6

Telegram Interface operates correctly.

REQ-12.2.7

Financial calculations operate correctly.

REQ-12.2.8

Statistics operate correctly.

REQ-12.2.9

Recovery operates correctly.

REQ-12.2.10

Settings operate correctly.

---

## 12.3 Operational Acceptance

REQ-12.3.1

The application SHALL operate continuously without manual intervention.

REQ-12.3.2

Unexpected restart SHALL NOT interrupt business operations.

REQ-12.3.3

Marketplace communication SHALL recover automatically.

REQ-12.3.4

Completed Orders SHALL never be duplicated.

REQ-12.3.5

Business history SHALL remain consistent.

---

## 12.4 Performance Acceptance

REQ-12.4.1

The system SHALL respond to operator actions without noticeable delay.

REQ-12.4.2

Marketplace monitoring SHALL operate continuously.

REQ-12.4.3

Automatic Reorder SHALL execute according to configured intervals.

REQ-12.4.4

Telegram notifications SHALL be delivered after significant business events.

---

## 12.5 Version Completion

SensFlow Version 1 SHALL be considered complete when:

REQ-12.5.1

All mandatory requirements defined in this document are implemented.

REQ-12.5.2

All acceptance criteria are satisfied.

REQ-12.5.3

All business workflows operate correctly.

REQ-12.5.4

The operator can perform the complete purchasing workflow using Telegram only.

REQ-12.5.5

Business data remains accurate after long-term operation.

REQ-12.5.6

The system successfully purchases Robux through RBXCreate using automated order management.

---

End of PROJECT_REQUIREMENTS.md