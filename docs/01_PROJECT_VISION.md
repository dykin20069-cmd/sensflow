# PROJECT VISION

Version: 1.0

Status: Final Draft

---

# Purpose

SensFlow is a Telegram-first automation platform designed to manage Robux purchases through the RBXCreate Marketplace.

The goal of the project is to eliminate repetitive manual work, reduce order completion time, maximize the number of completed customer orders, and provide the operator with a fast, reliable and convenient workflow.

SensFlow is not a marketplace.

RBXCreate remains the marketplace.

SensFlow is an intelligent management system built on top of it.

---

# Problem Statement

Today the purchasing process requires many repetitive actions:

- manually creating marketplace orders;
- manually searching for Roblox Place IDs;
- monitoring marketplace stock;
- cancelling and recreating orders;
- tracking completed purchases;
- calculating purchase costs;
- informing customers;
- keeping order history.

When multiple customer orders exist simultaneously, this workflow becomes slow, error-prone and difficult to scale.

---

# Vision

SensFlow should allow the operator to manage the entire purchasing process directly from Telegram.

The operator should no longer need to keep the RBXCreate website open continuously.

Routine operations should be automated while preserving full manual control whenever needed.

Every customer order should be tracked from creation until completion.

Every action should be recorded.

Every important event should generate a notification.

---

# Product Principles

SensFlow follows these principles:

- Telegram-first interface.
- Automation before manual work.
- Manual override is always available.
- Business safety has higher priority than speed.
- Complete order history.
- Deterministic behaviour.
- Automatic recovery after failures.
- Modular architecture.
- Production-ready quality.

---

# Primary Objectives

Version 1 must provide:

- Customer management.
- Automatic Roblox Place ID discovery.
- Manual Place ID entry.
- Draft Orders.
- PreOrders.
- Active Orders.
- Marketplace synchronization.
- Automatic stock monitoring.
- Automatic Marketplace Order recreation.
- Manual Marketplace Order recreation.
- Intelligent order scheduling.
- Financial calculations.
- Telegram notifications.
- Statistics.
- Recovery after restart.
- Complete timeline for every order.

---

# Long-Term Vision

Future versions may include:

- Multiple marketplaces.
- Multiple operators.
- Customer web dashboard.
- Advanced analytics.
- AI-assisted purchasing strategies.
- Dynamic scheduling strategies.
- Automatic exchange rate updates.
- Supplier analytics.
- Mobile administration panel.

These features are outside the scope of Version 1.

---

# Success Criteria

Version 1 is considered successful if the operator can:

- create customer orders entirely from Telegram;
- complete purchases faster than using the marketplace manually;
- minimize manual intervention;
- safely recover after application restarts;
- manage dozens of simultaneous customer orders without losing data.

---

# Non-Goals

Version 1 does not aim to:

- replace RBXCreate;
- automate customer communication outside Telegram;
- support multiple marketplaces;
- provide public APIs;
- implement advanced AI decision making.

---

# Design Philosophy

Every feature added to SensFlow must satisfy at least one of the following goals:

- reduce manual work;
- reduce purchase time;
- improve operator experience;
- improve reliability;
- improve scalability;
- improve business visibility.

Features that do not support these goals should not be included in Version 1.

---

End of document.