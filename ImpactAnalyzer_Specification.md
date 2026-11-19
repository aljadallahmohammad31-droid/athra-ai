# Impact Analyzer Enterprise v2 - Specifications & Features

## Executive Summary
The Impact Analyzer is an advanced, enterprise-grade requirements impact analysis and change governance platform built specifically for complex customs and government digital transformation initiatives (such as GCC-CUA integrations and National Customs Intelligence platforms like MEKSHAF). It bridges the gap between high-level strategic business requirements and granular technical dependencies across databases, APIs, and microservices.

---

## Key Upgraded Features in v2

### 1. Executive Risk Scoring & Severity Metrics
* **Overall Change Risk Score**: Instantly calculates a composite risk index (e.g., `78/100 – High Complexity`) based on downstream dependency breadth, core database alterations, and active concurrent change requests.
* **Clickable Severity Filter Strip**: Filter the strategy graph dynamically by severity tier (`Critical: 5`, `Moderate: 3`, `Low: 3`, `Unaffected: 1`).

### 2. Effort & SLA Estimator
* Translates architectural impact into concrete project management metrics right inside the `Impact Inspector` panel.
* **Metrics Tracked**: Estimated development days (`~14 Dev Days`), regression testing hours (`38 QA Hrs`), and required departmental sign-offs (`+1 Dept Sign-off`).

### 3. "What-If" Scope & Descoping Simulator
* Enables live sandbox toggling (e.g., `Freeze Core` or `Defer REQ-002`) to immediately visualize how descoping specific requirements reduces the overall blast radius and regression risk.

### 4. API & Database Contract Diff Viewer
* Provides a granular schema inspection tab alongside `Database / BI` and `API / Service` nodes, detailing exact field additions, payload modifications, and backward-compatibility alerts for integrations like GCC-CUA.

### 5. Cross-CR Collision & Conflict Detector
* Automatically scans the repository for parallel Change Requests touching the same modules (e.g., `CR260019 also touches Declaration Management`), preventing integration deadlocks and merge conflicts before development starts.

### 6. Role-Based Departmental Sign-Off Readiness
* Upgrades single-status reviews to a structured progress bar (`2/4 Approved`) spanning critical stakeholders:
  * Customs Operations (Approved)
  * GCC Integration Architect (Approved)
  * Risk & Selectivity Lead (Pending)
  * BI Analytics Team (Pending)

### 7. One-Click ALM / DevOps Push
* Integrated directly into the bottom action bar alongside `Export PDF`, allowing engineers and scrum masters to instantly push impacted modules, dependencies, and auto-generated UAT test cases (`UAT-MOD-01`, `TEST-001`) directly into Azure DevOps or Jira backlogs.
