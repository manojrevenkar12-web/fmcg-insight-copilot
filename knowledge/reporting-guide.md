---
id: reporting-guide
title: How to use the insight copilot
---

## What the copilot can answer
The copilot answers questions about governed KPIs for procurement, manufacturing and sales: spend, purchase price variance, supplier OTIF, rejection rate, OEE, availability, scrap, output, downtime, net revenue, volume, promotion share, return rate and net price. It can break them down by supplier, material, plant, line, downtime reason, country, customer, channel, brand, product and time, and compare with the previous period.

## What it does not do
It does not forecast, does not change data and does not answer questions outside the KPI catalog. It never writes its own SQL: every number comes from a governed KPI definition, and the definition, owner, SQL and lineage are shown with each answer.

## Data freshness
The consumption layer is refreshed daily at 06:00 CET from the ERP, MES and order-management extracts. Each answer states the as-of date of the data it used.

## Access to data
Users see only the countries they are entitled to. A Dutch sales manager sees Dutch sales; a plant manager sees their plant's country. Access rules are applied by the semantic layer, not by the AI.

## Official numbers
The monthly BI reports remain the official figures for management reporting. The copilot uses the same consumption layer and KPI definitions, so the numbers match; it adds speed and context, not a second version of the truth.

## Responsible use
The copilot is a decision-support tool. Its answers explain what the data shows; decisions on suppliers, maintenance or promotions stay with the business owners. Rate each answer so the AI team can improve it.
