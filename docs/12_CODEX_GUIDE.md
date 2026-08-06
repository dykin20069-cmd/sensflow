# CODEX DEVELOPMENT GUIDE

Document

CODEX_GUIDE

Version

1.0

Status

Final Draft

---

# 1. PURPOSE

This document is the primary implementation guide for Codex.

The objective is to ensure that every implementation decision follows the project documentation.

Codex SHALL prioritize correctness, maintainability and simplicity over unnecessary optimization.

If multiple implementation options exist, the simplest solution satisfying all documented requirements SHALL be selected.

---

# 2. REQUIRED READING ORDER

Before writing any code, Codex SHALL read the documentation in the following order:

README.md

↓

00_INDEX.md

↓

01_PROJECT_VISION.md

↓

02_PROJECT_REQUIREMENTS.md

↓

03_DATABASE.md

↓

04_ARCHITECTURE.md

↓

05_TELEGRAM_UI.md

↓

06_RBXCREATE_API.md

↓

07_ALGORITHMS.md

↓

08_BUSINESS_RULES.md

↓

09_IMPLEMENTATION_PLAN.md

↓

10_DEPLOYMENT.md

↓

11_TESTING.md

↓

12_CODEX_GUIDE.md

No implementation SHALL begin before all documentation has been reviewed.

---

# 3. TECHNOLOGY STACK

The implementation SHALL use:

Python 3.13

aiogram 3.x

PostgreSQL 17

SQLAlchemy 2.x

Alembic

Pydantic v2

Docker

Docker Compose

httpx

uv

Ruff

Pytest

Alternative technologies SHALL NOT be introduced without explicit approval.

---

# 4. DEVELOPMENT PRINCIPLES

Always implement documented requirements.

Never invent new features.

Never remove documented functionality.

Keep business logic independent from Telegram.

Keep business logic independent from RBXCreate.

Prefer readability over clever implementations.

Every function SHALL have one responsibility.

Large functions SHOULD be divided into smaller functions.

Avoid unnecessary abstraction.

---

# 5. IMPLEMENTATION ORDER

Codex SHALL implement the project in the following order:

1. Project structure

2. Configuration

3. Database

4. Repository layer

5. Business models

6. Business services

7. Telegram interface

8. RBXCreate integration

9. Scheduler

10. Automation

11. Statistics

12. Notifications

13. Testing

14. Final validation

Implementation SHALL follow this order unless explicitly instructed otherwise.

---

# 6. PROJECT STRUCTURE

The project SHALL be divided into logical modules.

Business logic SHALL remain separated from infrastructure.

Database models SHALL remain separated from Telegram.

External APIs SHALL remain isolated.

Configuration SHALL remain centralized.

---

# 7. DATABASE RULES

Database schema SHALL follow DATABASE.md.

Business entities SHALL NOT be modified outside repositories.

Completed Orders SHALL remain immutable.

Historical data SHALL never be deleted automatically.

Migrations SHALL be managed through Alembic.

---

# 8. TELEGRAM RULES

Telegram SHALL contain presentation logic only.

Business calculations SHALL NOT occur inside handlers.

Handlers SHALL delegate work to Business Services.

The Telegram interface SHALL remain responsive.

---

# 9. MARKETPLACE RULES

RBXCreate SHALL be accessed only through the Marketplace module.

HTTP requests SHALL be isolated.

Unexpected API failures SHALL never corrupt business data.

Synchronization SHALL update Client Orders only after successful validation.

---

# 10. BUSINESS RULES

Every implementation SHALL respect BUSINESS_RULES.md.

If implementation conflicts with Business Rules, Business Rules take priority.

Business Rules SHALL NOT be duplicated in code comments.

---

# 11. ERROR HANDLING

Unexpected exceptions SHALL be handled gracefully.

Business entities SHALL remain consistent.

Critical failures SHALL be logged.

Recoverable failures SHALL trigger retry where appropriate.

---

# 12. LOGGING

Business events SHALL be logged.

Marketplace communication SHALL be logged.

Unexpected exceptions SHALL be logged.

Sensitive information SHALL NOT appear in logs.

---

# 13. TESTING

Every implemented module SHALL include tests.

Business workflows SHALL be validated.

Recovery SHALL be tested.

Marketplace integration SHALL be testable without production data whenever possible.

---

# 14. GIT WORKFLOW

Development SHALL proceed using small commits.

Each commit SHALL implement one logical unit of work.

Commit messages SHALL clearly describe the implemented functionality.

---

# 15. DEFINITION OF DONE

A task SHALL be considered complete only when:

Implementation is finished.

Code builds successfully.

Tests pass.

Documentation remains consistent.

No Business Rules are violated.

No new warnings are introduced.

---

# 16. FORBIDDEN BEHAVIOR

Codex SHALL NOT:

Invent undocumented functionality.

Modify documentation silently.

Ignore Business Rules.

Change architecture without approval.

Replace libraries without approval.

Delete historical business data.

Duplicate business logic.

Hardcode configuration values.

---

# 17. SELF REVIEW

After completing every implementation task, Codex SHALL verify:

Architecture compliance.

Business Rule compliance.

Database consistency.

Telegram workflow.

Marketplace workflow.

Recovery behavior.

Error handling.

Code readability.

---

# 18. FINAL OBJECTIVE

The goal of Version 1 is to deliver a production-ready Telegram-first Robux purchasing automation platform.

The implementation SHALL prioritize reliability, maintainability and correctness.

Version 1 SHALL remain intentionally simple.

Additional functionality belongs to future versions unless explicitly documented.

---

End of CODEX_GUIDE.md