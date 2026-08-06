# SensFlow Documentation Index

Version: 1.0

Status: Draft

---

# Purpose

This document is the entry point for the entire SensFlow specification.

Every developer and every AI coding assistant (Codex) MUST start reading here before implementing any part of the system.

This document defines:

- documentation structure;
- reading order;
- dependencies between documents;
- implementation workflow.

---

# Documentation Reading Order

Read the documents in the following order:

1. PROJECT_VISION
2. PROJECT_REQUIREMENTS
3. DATABASE
4. ARCHITECTURE
5. TELEGRAM_UI
6. RBXCREATE_API
7. ALGORITHMS
8. BUSINESS_RULES
9. IMPLEMENTATION_PLAN
10. DEPLOYMENT
11. TESTING
12. CODEX_GUIDE

Reading documents in another order is not recommended.

---

# Purpose of Each Document

## 01_PROJECT_VISION

Explains the business idea, philosophy and long-term goals of SensFlow.

---

## 02_PROJECT_REQUIREMENTS

Contains the complete functional specification.

Defines WHAT the system must do.

---

## 03_DATABASE

Defines every database entity, relationship and storage rule.

---

## 04_ARCHITECTURE

Defines modules, services and responsibilities.

Defines HOW the system is built.

---

## 05_TELEGRAM_UI

Defines every Telegram screen, menu, button and operator workflow.

---

## 06_RBXCREATE_API

Defines RBXCreate integration.

Authentication.

Marketplace communication.

Order synchronization.

---

## 07_ALGORITHMS

Defines all business algorithms.

Order lifecycle.

Scheduling.

Reordering.

Recovery.

Notifications.

---

## 08_BUSINESS_RULES

Defines immutable business rules.

These rules have higher priority than implementation decisions.

---

## 09_IMPLEMENTATION_PLAN

Defines the exact implementation order.

Every phase must be completed before starting the next one.

---

## 10_DEPLOYMENT

Defines production deployment.

Docker.

Configuration.

Startup.

Recovery.

---

## 11_TESTING

Defines testing strategy.

Unit Tests.

Integration Tests.

Stress Tests.

Recovery Tests.

---

## 12_CODEX_GUIDE

Step-by-step instructions for implementing the project with Codex.

---

# Document Priority

If documents contradict each other, priority is:

1. BUSINESS_RULES
2. PROJECT_REQUIREMENTS
3. ALGORITHMS
4. ARCHITECTURE
5. DATABASE
6. Remaining documents

---

# Development Workflow

Specification

↓

Architecture

↓

Database

↓

Implementation

↓

Testing

↓

Deployment

↓

Release

---

# Current Project Status

Documentation: In Progress

Implementation: Not Started

Production: Not Started

---

End of document.