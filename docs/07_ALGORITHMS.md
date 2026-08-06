# BUSINESS ALGORITHMS

Document

ALGORITHMS

Version

1.0

Status

Final Draft

---

# 1. PURPOSE

This document defines the business algorithms used by SensFlow Version 1.

Algorithms describe business behavior independently of programming language or implementation.

Every implementation SHALL follow these algorithms.

---

# 2. DESIGN PRINCIPLES

ALG-2.1

Algorithms SHALL be deterministic.

ALG-2.2

The same input SHALL always produce the same result.

ALG-2.3

Algorithms SHALL never corrupt business entities.

ALG-2.4

Automation SHALL always be recoverable after restart.

ALG-2.5

Business correctness has higher priority than execution speed.

---

# 3. CUSTOMER CREATION ALGORITHM

Input:

Roblox Username

Process:

1. Search existing Customer.

2. If Customer exists:

Return existing Customer.

3. Otherwise:

Request Roblox User ID.

4. Create Customer.

5. Search Place ID.

6. Save Customer.

Output:

Customer ready for Client Order creation.

---

# 4. PLACE ID DISCOVERY ALGORITHM

Input:

Roblox Username

Process:

Step 1

Check stored Customer data.

↓

If Place ID exists

↓

Use stored Place ID.

↓

Otherwise

↓

Request Roblox API.

↓

If successful

↓

Store Place ID.

↓

Otherwise

↓

Operator enters Place ID manually.

Output:

Valid Place ID.

---

# 5. CLIENT ORDER CREATION

Input:

Customer

Requested Robux

Process:

Create Draft Order.

Store Customer.

Store Requested Robux.

Store Place ID.

Wait for payment confirmation.

Output:

Draft Order.

---

# 6. PAYMENT CONFIRMATION

Input:

Draft Order

Process:

Check Marketplace Stock.

If stock satisfies Maximum Purchase Rate:

↓

Transition to Purchasing.

↓

Create Marketplace Order.

Otherwise:

↓

Transition to PreOrder.

Output:

Purchasing or PreOrder.

---

# 7. STOCK MONITORING

The application continuously monitors Marketplace stock.

Whenever suitable stock appears:

Scheduler SHALL immediately evaluate waiting PreOrders.

If no suitable stock exists:

Continue monitoring.

---

# 8. SCHEDULER ALGORITHM

Version 1 SHALL implement one scheduling strategy.

Strategy:

Maximum Customers.

Input:

Available Marketplace Stock.

Waiting PreOrders.

Process:

Sort waiting Client Orders.

Calculate combinations.

Select the combination completing the greatest number of customers.

Transition selected orders to Purchasing.

Leave remaining orders in PreOrder.

Output:

Purchasing Orders.

---

# 9. MARKETPLACE ORDER CREATION

Input:

Purchasing Order.

Process:

Create Marketplace Order.

Store Marketplace Order ID.

Start synchronization.

Start Automatic Reorder.

Output:

Marketplace Order.

---

# 10. AUTOMATIC REORDER

Input:

Purchasing Order.

Process:

Wait configured interval.

↓

Check Marketplace status.

↓

If completed

↓

Stop.

↓

Otherwise

↓

Cancel Marketplace Order.

↓

Wait confirmation.

↓

Create new Marketplace Order.

↓

Continue monitoring.

Output:

Updated Marketplace Order.

---

# 11. MANUAL REORDER

Input:

Operator request.

Process:

Cancel Marketplace Order.

Wait cancellation confirmation.

Create replacement Marketplace Order.

Continue synchronization.

Output:

Updated Marketplace Order.

---

# 12. PURCHASE COMPLETION

Input:

Marketplace reports completed purchase.

Process:

Stop Automatic Reorder.

Stop monitoring.

Calculate Final Cost.

Calculate Marketplace Commission.

Calculate Local Currency.

Update Statistics.

Create Timeline event.

Send Telegram notification.

Transition Client Order to Completed.

Output:

Completed Client Order.

---

# 13. RECOVERY ALGORITHM

Application Restart

↓

Load System Settings.

↓

Load Customers.

↓

Load Client Orders.

↓

Load Purchasing Orders.

↓

Resume Synchronization.

↓

Resume Stock Monitoring.

↓

Resume Automatic Reorder.

↓

System Ready.

---

# 14. ERROR RECOVERY

Temporary failures:

Retry.

Permanent failures:

Notify operator.

Unexpected failures:

Write System Log.

Business entities SHALL remain consistent.

---

# 15. ALGORITHM ACCEPTANCE

ALG-15.1

Customer creation behaves correctly.

ALG-15.2

Place ID discovery behaves correctly.

ALG-15.3

Scheduler selects the proper Client Orders.

ALG-15.4

Automatic Reorder behaves correctly.

ALG-15.5

Manual Reorder behaves correctly.

ALG-15.6

Completed purchases are finalized correctly.

ALG-15.7

Recovery restores the application correctly.

---

End of ALGORITHMS.md