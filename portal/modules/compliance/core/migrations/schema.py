"""Versioned DDL for the canonical compliance store (P2).

Each entry is one forward-only migration: ``(version, description, sql)``.
``core.repository.Repository.migrate()`` applies every version greater than
the store's recorded ``schema_version`` inside one transaction, and records
the new version only on success — a failure mid-migration leaves the store
at its last good version, not half-upgraded.

Tables beyond ``001`` correspond 1:1 to DESIGN_COMPLIANCE_REASONING_V2 §4's
entity-family table. Families P2 does not yet populate (``obligation_atoms``,
``internal_controls``, ``claims``/``findings``, ``policy_decisions``/
``change_scenarios``/``work_items``, ``entity_profiles``/``scope_revisions``)
still get their schema now, so a later phase adds ROWS, never another
migration to invent the table.
"""

from __future__ import annotations

MIGRATIONS: list[tuple[int, str, str]] = [
    (
        1,
        "core: source documents, revisions, sections, spans",
        """
        CREATE TABLE source_documents (
            logical_id   TEXT PRIMARY KEY,
            title        TEXT NOT NULL,
            issuer       TEXT NOT NULL DEFAULT '',
            source_kind  TEXT NOT NULL DEFAULT 'unknown',
            jurisdiction TEXT NOT NULL DEFAULT '',
            org_id       TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE document_revisions (
            revision_id       TEXT PRIMARY KEY,          -- sha256(bytes)
            logical_id        TEXT NOT NULL REFERENCES source_documents(logical_id),
            alias_path        TEXT NOT NULL,
            binding_effect    TEXT NOT NULL DEFAULT 'unknown',
            authored_date     TEXT,
            approved_date     TEXT,
            effective_date    TEXT,
            last_reviewed_date TEXT,
            retrieved_at      TEXT NOT NULL,
            org_id            TEXT NOT NULL DEFAULT 'default',
            recorded_from     TEXT NOT NULL,
            recorded_to       TEXT
        );
        CREATE INDEX ix_document_revisions_logical ON document_revisions(logical_id);
        CREATE INDEX ix_document_revisions_alias ON document_revisions(alias_path);

        CREATE TABLE source_sections (
            section_id        TEXT PRIMARY KEY,
            revision_id       TEXT NOT NULL REFERENCES document_revisions(revision_id),
            path              TEXT NOT NULL,
            page_start        INTEGER,
            page_end          INTEGER,
            table_ref         TEXT,
            extractor         TEXT NOT NULL DEFAULT '',
            extractor_version TEXT NOT NULL DEFAULT '',
            org_id            TEXT NOT NULL DEFAULT 'default'
        );
        CREATE INDEX ix_source_sections_revision ON source_sections(revision_id);

        CREATE TABLE source_spans (
            span_id     TEXT PRIMARY KEY,
            section_id  TEXT NOT NULL REFERENCES source_sections(section_id),
            char_start  INTEGER NOT NULL,
            char_end    INTEGER NOT NULL,
            text_sha256 TEXT NOT NULL,
            org_id      TEXT NOT NULL DEFAULT 'default'
        );
        CREATE INDEX ix_source_spans_section ON source_spans(section_id);
        """,
    ),
    (
        2,
        "core: relationship assertions (proposal/effective separation) + review events",
        """
        CREATE TABLE relationship_assertions (
            assertion_id     TEXT PRIMARY KEY,
            relation_type    TEXT NOT NULL,
            src_ref          TEXT NOT NULL,
            src_revision_id  TEXT,
            dst_ref          TEXT NOT NULL,
            dst_revision_id  TEXT,
            scope            TEXT NOT NULL DEFAULT '',
            citations_json   TEXT NOT NULL DEFAULT '[]',
            status           TEXT NOT NULL DEFAULT 'proposed'
                             CHECK (status IN ('proposed','approved','rejected','revoked','stale')),
            review_state     TEXT NOT NULL DEFAULT 'proposed',
            valid_from       TEXT,
            valid_to         TEXT,
            recorded_from    TEXT NOT NULL,
            recorded_to      TEXT,
            rationale        TEXT NOT NULL DEFAULT '',
            decided_by       TEXT NOT NULL DEFAULT '',
            decided_at       TEXT,
            version          INTEGER NOT NULL DEFAULT 1,
            org_id           TEXT NOT NULL DEFAULT 'default'
        );
        -- Both endpoints indexed for bidirectional traversal (design §4).
        CREATE INDEX ix_rel_src ON relationship_assertions(src_ref, status);
        CREATE INDEX ix_rel_dst ON relationship_assertions(dst_ref, status);

        CREATE TABLE review_events (
            event_id          TEXT PRIMARY KEY,
            target_type       TEXT NOT NULL,
            target_id         TEXT NOT NULL,
            expected_version  INTEGER NOT NULL,
            decision          TEXT NOT NULL,
            decided_by        TEXT NOT NULL,
            rationale         TEXT NOT NULL DEFAULT '',
            evidence_json     TEXT NOT NULL DEFAULT '[]',
            created_at        TEXT NOT NULL,
            prior_event_id    TEXT NOT NULL DEFAULT '',
            org_id            TEXT NOT NULL DEFAULT 'default'
        );
        CREATE INDEX ix_review_events_target ON review_events(target_type, target_id);
        """,
    ),
    (
        3,
        "core: outbox + catalog/corpus snapshots + index manifests",
        """
        CREATE TABLE outbox_events (
            event_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type   TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at   TEXT NOT NULL,
            published_at TEXT
        );
        CREATE INDEX ix_outbox_unpublished ON outbox_events(published_at);

        CREATE TABLE catalog_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            taken_at    TEXT NOT NULL,
            counts_json TEXT NOT NULL DEFAULT '{}',
            hashes_json TEXT NOT NULL DEFAULT '{}',
            org_id      TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE corpus_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            taken_at    TEXT NOT NULL,
            counts_json TEXT NOT NULL DEFAULT '{}',
            hashes_json TEXT NOT NULL DEFAULT '{}',
            org_id      TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE index_manifests (
            generation_id TEXT PRIMARY KEY,
            index_kind    TEXT NOT NULL,
            created_at    TEXT NOT NULL,
            active        INTEGER NOT NULL DEFAULT 0,
            counts_json   TEXT NOT NULL DEFAULT '{}',
            org_id        TEXT NOT NULL DEFAULT 'default'
        );
        """,
    ),
    (
        4,
        "domain (schema-only, unpopulated until P3-P7): obligations, effectivity/authority, "
        "scope, operational entities, analysis/claims/findings, policy/scenario/work items",
        """
        CREATE TABLE standard_revisions (
            revision_id  TEXT PRIMARY KEY,
            logical_id   TEXT NOT NULL,
            family       TEXT NOT NULL,
            version      TEXT NOT NULL,
            org_id       TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE requirement_nodes (
            node_id            TEXT PRIMARY KEY,
            standard_revision_id TEXT NOT NULL REFERENCES standard_revisions(revision_id),
            requirement        TEXT NOT NULL,
            part               TEXT NOT NULL DEFAULT '',
            logical_lineage_id TEXT NOT NULL DEFAULT '',
            org_id             TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE obligation_atoms (
            atom_id             TEXT PRIMARY KEY,
            node_id             TEXT NOT NULL REFERENCES requirement_nodes(node_id),
            actor               TEXT NOT NULL DEFAULT '',
            modality             TEXT NOT NULL DEFAULT '',
            action              TEXT NOT NULL DEFAULT '',
            object              TEXT NOT NULL DEFAULT '',
            population          TEXT NOT NULL DEFAULT '',
            trigger             TEXT NOT NULL DEFAULT '',
            deadline_cadence    TEXT NOT NULL DEFAULT '',
            conditions_json     TEXT NOT NULL DEFAULT '[]',
            exceptions_json     TEXT NOT NULL DEFAULT '[]',
            evidence_expectation TEXT NOT NULL DEFAULT '',
            source_anchor_ids_json TEXT NOT NULL DEFAULT '[]',
            interpretation_status TEXT NOT NULL DEFAULT 'proposed',
            org_id              TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE obligation_expressions (
            expression_id TEXT PRIMARY KEY,
            node_id       TEXT NOT NULL REFERENCES requirement_nodes(node_id),
            structure_json TEXT NOT NULL DEFAULT '{}',  -- ALL_OF | ANY_OF | AT_LEAST_N | conditional
            org_id        TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE definitions (
            definition_id TEXT PRIMARY KEY,
            term          TEXT NOT NULL,
            body          TEXT NOT NULL DEFAULT '',
            source_anchor_id TEXT,
            org_id        TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE effectivity_assertions (
            assertion_id  TEXT PRIMARY KEY,
            node_id       TEXT NOT NULL REFERENCES requirement_nodes(node_id),
            jurisdiction  TEXT NOT NULL DEFAULT '',
            valid_from    TEXT,
            valid_to      TEXT,
            recorded_from TEXT NOT NULL,
            recorded_to   TEXT,
            source_anchor_id TEXT,
            approval_status TEXT NOT NULL DEFAULT 'unverified',
            org_id        TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE authority_assertions (
            assertion_id  TEXT PRIMARY KEY,
            revision_id   TEXT NOT NULL REFERENCES document_revisions(revision_id),
            source_kind   TEXT NOT NULL DEFAULT 'unknown',
            binding_effect TEXT NOT NULL DEFAULT 'unknown',
            approval_status TEXT NOT NULL DEFAULT 'unverified',
            approval_source_anchor_id TEXT,
            verified_at   TEXT,
            org_id        TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE entity_profiles (
            entity_id   TEXT PRIMARY KEY,
            name        TEXT NOT NULL DEFAULT '',
            org_id      TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE scope_revisions (
            scope_revision_id TEXT PRIMARY KEY,
            entity_id         TEXT NOT NULL REFERENCES entity_profiles(entity_id),
            registered_functions_json TEXT NOT NULL DEFAULT '[]',
            jurisdiction      TEXT NOT NULL DEFAULT '',
            populations_json  TEXT NOT NULL DEFAULT '[]',
            status            TEXT NOT NULL DEFAULT 'candidate',  -- candidate | approved
            valid_from        TEXT,
            valid_to          TEXT,
            recorded_from     TEXT NOT NULL,
            recorded_to       TEXT,
            org_id            TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE asset_groups (
            group_id   TEXT PRIMARY KEY,
            entity_id  TEXT NOT NULL REFERENCES entity_profiles(entity_id),
            category   TEXT NOT NULL DEFAULT '',
            org_id     TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE internal_controls (
            control_id  TEXT PRIMARY KEY,
            revision_id TEXT NOT NULL REFERENCES document_revisions(revision_id),
            title       TEXT NOT NULL DEFAULT '',
            org_id      TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE activities (
            activity_id TEXT PRIMARY KEY,
            control_id  TEXT REFERENCES internal_controls(control_id),
            cadence     TEXT NOT NULL DEFAULT '',
            org_id      TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE roles (
            role_id   TEXT PRIMARY KEY,
            name      TEXT NOT NULL,
            org_id    TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE systems (
            system_id TEXT PRIMARY KEY,
            name      TEXT NOT NULL,
            org_id    TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE evidence_specs (
            spec_id     TEXT PRIMARY KEY,
            control_id  TEXT REFERENCES internal_controls(control_id),
            description TEXT NOT NULL DEFAULT '',
            org_id      TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE evidence_artifacts (
            artifact_id TEXT PRIMARY KEY,
            spec_id     TEXT REFERENCES evidence_specs(spec_id),
            period      TEXT NOT NULL DEFAULT '',
            revision_id TEXT REFERENCES document_revisions(revision_id),
            org_id      TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE analysis_runs (
            run_id      TEXT PRIMARY KEY,
            context_json TEXT NOT NULL DEFAULT '{}',
            created_at  TEXT NOT NULL,
            org_id      TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE claims (
            claim_id       TEXT PRIMARY KEY,
            run_id         TEXT NOT NULL REFERENCES analysis_runs(run_id),
            obligation_atom_ids_json TEXT NOT NULL DEFAULT '[]',
            claim_kind     TEXT NOT NULL DEFAULT '',
            review_status  TEXT NOT NULL DEFAULT 'proposed',
            assertion      TEXT NOT NULL DEFAULT '',
            rationale      TEXT NOT NULL DEFAULT '',
            governing_anchor_ids_json TEXT NOT NULL DEFAULT '[]',
            internal_anchor_ids_json TEXT NOT NULL DEFAULT '[]',
            counterevidence_anchor_ids_json TEXT NOT NULL DEFAULT '[]',
            created_at     TEXT NOT NULL,
            org_id         TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE claim_evidence (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_id   TEXT NOT NULL REFERENCES claims(claim_id),
            anchor_id  TEXT NOT NULL,
            role       TEXT NOT NULL DEFAULT 'supporting'  -- supporting | contradicting
        );

        CREATE TABLE findings (
            finding_id  TEXT PRIMARY KEY,
            claim_id    TEXT NOT NULL REFERENCES claims(claim_id),
            finding_kind TEXT NOT NULL DEFAULT '',
            org_id      TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE policy_decisions (
            decision_id TEXT PRIMARY KEY,
            control_id  TEXT REFERENCES internal_controls(control_id),
            rationale   TEXT NOT NULL DEFAULT '',
            owner       TEXT NOT NULL DEFAULT '',
            approving_authority TEXT NOT NULL DEFAULT '',
            review_date TEXT,
            org_id      TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE change_scenarios (
            scenario_id     TEXT PRIMARY KEY,
            base_revision_id TEXT NOT NULL REFERENCES document_revisions(revision_id),
            patch           TEXT NOT NULL DEFAULT '',
            rationale       TEXT NOT NULL DEFAULT '',
            scope           TEXT NOT NULL DEFAULT '',
            planned_effective_date TEXT,
            created_at      TEXT NOT NULL,
            org_id          TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE work_items (
            work_item_id TEXT PRIMARY KEY,
            scenario_id  TEXT REFERENCES change_scenarios(scenario_id),
            owner        TEXT NOT NULL DEFAULT '',
            due_date     TEXT,
            status       TEXT NOT NULL DEFAULT 'open',
            org_id       TEXT NOT NULL DEFAULT 'default'
        );
        """,
    ),
]
