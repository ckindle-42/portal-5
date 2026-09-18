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
    (
        5,
        "coverage-bearing relationships (mapping_store consolidation onto Repository)",
        """
        -- TASK_COMPLIANCE_STORE_CONSOLIDATION_V1: mapping_store.py's
        -- requirement->document coverage judgement (FULL/PARTIAL/NONE/...)
        -- is a property of a relationship_assertions row, not a separate
        -- data model — a requirement<->document edge with a coverage
        -- verdict IS the same edge compliance_trace already traverses.
        -- Nullable/defaulted so every pre-existing row is unaffected.
        ALTER TABLE relationship_assertions ADD COLUMN coverage TEXT NOT NULL DEFAULT '';
        ALTER TABLE relationship_assertions ADD COLUMN proposed_coverage TEXT NOT NULL DEFAULT '';
        ALTER TABLE relationship_assertions ADD COLUMN confidence REAL NOT NULL DEFAULT 0.0;
        """,
    ),
    (
        6,
        "reasoning v3: determination contract and corpus boundary proofs",
        """
        CREATE TABLE corpus_boundary_proofs (
            boundary_proof_id TEXT PRIMARY KEY,
            subject_ref TEXT NOT NULL,
            query_set_json TEXT NOT NULL,
            index_generation TEXT NOT NULL,
            manifest_hash TEXT NOT NULL,
            eligible_document_count INTEGER NOT NULL,
            candidates_retrieved_json TEXT NOT NULL DEFAULT '[]',
            candidates_rejected_json TEXT NOT NULL DEFAULT '[]',
            truncation_flags_json TEXT NOT NULL DEFAULT '[]',
            budget_ceilings_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            org_id TEXT NOT NULL DEFAULT 'default',
            CHECK (length(trim(query_set_json)) > 2),
            CHECK (length(trim(index_generation)) > 0)
        );

        CREATE TABLE claims_v3 (
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
            org_id         TEXT NOT NULL DEFAULT 'default',
            determination TEXT NOT NULL DEFAULT 'UNRESOLVED'
                CHECK (determination IN ('SUPPORTED','PARTIAL','CONTRADICTED','ABSENT','UNRESOLVED')),
            unresolved_code TEXT NOT NULL DEFAULT '',
            missing_fact_json TEXT NOT NULL DEFAULT '{}',
            field_results_json TEXT NOT NULL DEFAULT '[]',
            boundary_proof_id TEXT NOT NULL DEFAULT '',
            CHECK (determination <> 'UNRESOLVED' OR unresolved_code <> ''),
            CHECK (determination <> 'ABSENT' OR boundary_proof_id <> '')
        );

        INSERT INTO claims_v3 (
            claim_id, run_id, obligation_atom_ids_json, claim_kind, review_status,
            assertion, rationale, governing_anchor_ids_json, internal_anchor_ids_json,
            counterevidence_anchor_ids_json, created_at, org_id, determination,
            unresolved_code, missing_fact_json, field_results_json, boundary_proof_id
        )
        SELECT claim_id, run_id, obligation_atom_ids_json, claim_kind, review_status,
            assertion, rationale, governing_anchor_ids_json, internal_anchor_ids_json,
            counterevidence_anchor_ids_json, created_at, org_id, 'UNRESOLVED',
            'U03_EXTRACTION_FAILED',
            '{"legacy_claim":"determination was not recorded before schema v6"}', '[]', ''
        FROM claims;

        DROP TABLE claims;
        ALTER TABLE claims_v3 RENAME TO claims;
        """,
    ),
    (
        7,
        "reading architecture: one AssessmentResult authority + durable assessment runs",
        """
        -- The canonical run row gains the fields the asynchronous run service
        -- needs (brief §6 Execution boundary). Old rows default to COMPLETE and
        -- remain readable — a restart marks unfinished RUNNING jobs INTERRUPTED.
        ALTER TABLE analysis_runs ADD COLUMN status TEXT NOT NULL DEFAULT 'COMPLETE';
        ALTER TABLE analysis_runs ADD COLUMN request_json TEXT NOT NULL DEFAULT '{}';
        ALTER TABLE analysis_runs ADD COLUMN progress_json TEXT NOT NULL DEFAULT '{}';
        ALTER TABLE analysis_runs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE analysis_runs ADD COLUMN started_at TEXT;
        ALTER TABLE analysis_runs ADD COLUMN finished_at TEXT;
        ALTER TABLE analysis_runs ADD COLUMN updated_at TEXT;

        -- One row per assessed Part. The complete result JSON is the authority —
        -- the scalar columns are indexed projections for run/requirement lookup.
        CREATE TABLE assessment_results (
            assessment_id     TEXT PRIMARY KEY,
            run_id            TEXT NOT NULL REFERENCES analysis_runs(run_id),
            parent_assessment_id TEXT NOT NULL DEFAULT '',
            requirement_id    TEXT NOT NULL,
            engine_version    TEXT NOT NULL DEFAULT '',
            schema_version    INTEGER NOT NULL DEFAULT 0,
            org_id            TEXT NOT NULL DEFAULT 'default',
            kb_id             TEXT NOT NULL DEFAULT '',
            input_fingerprint TEXT NOT NULL DEFAULT '',
            effective_on      TEXT NOT NULL DEFAULT '',
            known_at          TEXT NOT NULL DEFAULT '',
            applicability     TEXT NOT NULL DEFAULT 'UNKNOWN',
            coverage          TEXT NOT NULL DEFAULT 'UNRESOLVED',
            documentary_coverage TEXT NOT NULL DEFAULT 'UNRESOLVED',
            substantively_resolved INTEGER NOT NULL DEFAULT 0,
            unresolved_code   TEXT NOT NULL DEFAULT '',
            result_json       TEXT NOT NULL DEFAULT '{}',
            created_at        TEXT NOT NULL,
            CHECK (documentary_coverage IN
                   ('FULL','PARTIAL','NONE','UNRESOLVED','NEEDS_REVIEW','NOT_APPLICABLE')),
            CHECK (documentary_coverage <> 'UNRESOLVED' OR unresolved_code <> '')
        );
        CREATE INDEX ix_assessment_run ON assessment_results(run_id);
        CREATE INDEX ix_assessment_requirement ON assessment_results(requirement_id);
        CREATE INDEX ix_assessment_fingerprint ON assessment_results(input_fingerprint);
        """,
    ),
    (
        8,
        "product contract (END_TO_END P1): separated result dimensions + source roles",
        # NOTE: this runner splits statements on ';' — never put one inside a
        # comment line inside a migration's SQL block.
        """
        -- §3.4: the canonical result carries readiness, currency, evidence and
        -- review-need as separate typed columns, not one collapsed coverage
        -- label. Legacy rows keep the honest defaults (UNKNOWN/NOT_ASSESSED)
        -- and remain fully readable. Nothing is back-filled to look ready.
        ALTER TABLE assessment_results ADD COLUMN source_readiness TEXT NOT NULL DEFAULT 'UNKNOWN';
        ALTER TABLE assessment_results ADD COLUMN temporal_currency TEXT NOT NULL DEFAULT 'UNKNOWN';
        ALTER TABLE assessment_results ADD COLUMN documentary_alignment TEXT NOT NULL DEFAULT 'UNRESOLVED';
        ALTER TABLE assessment_results ADD COLUMN implementation_evidence TEXT NOT NULL DEFAULT 'NOT_ASSESSED';
        ALTER TABLE assessment_results ADD COLUMN review_required INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE assessment_results ADD COLUMN review_reason TEXT NOT NULL DEFAULT '';

        -- §3.2: source sections carry a controlled role drawn from the
        -- result_contract.SOURCE_ROLES vocabulary. Empty means unclassified,
        -- never a guessed role.
        ALTER TABLE source_sections ADD COLUMN role TEXT NOT NULL DEFAULT '';
        """,
    ),
    (
        9,
        "complete regulatory semantics (END_TO_END P3): clause text, dependencies, "
        "duty concepts and semantic lineage",
        """
        -- P3: each obligation atom carries the verbatim clause it was derived
        -- from, so an atom can always be proven against the duty text. Legacy
        -- rows (single-heuristic atoms) keep an empty clause and read as
        -- unanchored until re-derived from the same source revision.
        ALTER TABLE obligation_atoms ADD COLUMN clause_text TEXT NOT NULL DEFAULT '';

        -- P3: explicit duty dependencies — 'identified in Part 2.1' becomes a
        -- row, not prose inside an atom field.
        CREATE TABLE obligation_dependencies (
            dependency_id    TEXT PRIMARY KEY,
            node_id          TEXT NOT NULL REFERENCES requirement_nodes(node_id),
            atom_id          TEXT NOT NULL REFERENCES obligation_atoms(atom_id),
            depends_on_node_id TEXT NOT NULL DEFAULT '',
            depends_on_ref   TEXT NOT NULL DEFAULT '',
            kind             TEXT NOT NULL DEFAULT 'references',
            org_id           TEXT NOT NULL DEFAULT 'default'
        );
        CREATE INDEX ix_obligation_deps_node ON obligation_dependencies(node_id);
        CREATE INDEX ix_obligation_deps_target ON obligation_dependencies(depends_on_node_id);

        -- P3: stable semantic duty concepts. A concept may span revisions;
        -- membership is recorded on requirement_nodes.logical_lineage_id and
        -- is computed from duty text correspondence — part numbering is
        -- evidence, never the identity rule.
        CREATE TABLE obligation_concepts (
            concept_id   TEXT PRIMARY KEY,
            family       TEXT NOT NULL DEFAULT '',
            label        TEXT NOT NULL DEFAULT '',
            derivation   TEXT NOT NULL DEFAULT '',
            org_id       TEXT NOT NULL DEFAULT 'default'
        );
        """,
    ),
    (
        10,
        "internal corpus (END_TO_END P4): sourced revision metadata, section "
        "titles, and mapping derivation",
        # NOTE: this runner splits statements on ';' — never put one inside a
        # comment line inside a migration's SQL block.
        """
        -- P4: controlled-document metadata read from the document's own
        -- control block. Empty string means absent/unsourced — never guessed
        -- from a filename or defaulted.
        ALTER TABLE document_revisions ADD COLUMN document_number TEXT NOT NULL DEFAULT '';
        ALTER TABLE document_revisions ADD COLUMN version TEXT NOT NULL DEFAULT '';
        ALTER TABLE document_revisions ADD COLUMN owner TEXT NOT NULL DEFAULT '';
        ALTER TABLE document_revisions ADD COLUMN owner_title TEXT NOT NULL DEFAULT '';

        -- P4: section heading titles beside the structural path, so an
        -- operative section resolves by its own name.
        ALTER TABLE source_sections ADD COLUMN title TEXT NOT NULL DEFAULT '';

        -- P4: how a mapping assertion was derived. Folder/prefix Cartesian
        -- candidates carry 'folder_cartesian' and are excluded from
        -- established trace and deterministic impact. Empty means the
        -- pre-P4 legacy derivation recorded only in rationale.
        ALTER TABLE relationship_assertions ADD COLUMN derivation TEXT NOT NULL DEFAULT '';
        """,
    ),
    (
        11,
        "faithful whole-document capture (BILATERAL_CORPUS_V1 P1): positional "
        "units, document coordinate space, structured tables",
        # NOTE: this runner splits statements on ';' -- never put one inside a
        # comment line inside a migration's SQL block (rule R9).
        """
        -- P1: what kind of positional unit a section is. Purely structural --
        -- prose, table, table_row, list_item, figure_caption. Empty string on
        -- every pre-P1 row, which is how a legacy section is recognised.
        ALTER TABLE source_sections ADD COLUMN unit_kind TEXT NOT NULL DEFAULT '';

        -- P1: reading order within the revision, 0-based. -1 means the
        -- extractor did not record one.
        ALTER TABLE source_sections ADD COLUMN ordinal INTEGER NOT NULL DEFAULT -1;

        -- P1: the section's half-open span in the revision's captured text
        -- (document_texts.full_text). -1 means unanchored. source_spans keeps
        -- its own rows and these columns make the tiling queryable without a join
        -- and are what the fidelity gates read.
        ALTER TABLE source_sections ADD COLUMN char_start INTEGER NOT NULL DEFAULT -1;
        ALTER TABLE source_sections ADD COLUMN char_end INTEGER NOT NULL DEFAULT -1;

        -- P1: the heading lineage the unit sits under, from the document's own
        -- outline. Never inferred from content.
        ALTER TABLE source_sections ADD COLUMN heading_path TEXT NOT NULL DEFAULT '';

        CREATE INDEX ix_source_sections_ordinal ON source_sections(revision_id, ordinal);
        CREATE INDEX ix_source_sections_table ON source_sections(table_ref);

        -- P1: the captured document text -- the one character coordinate space
        -- a revision's sections tile. Held here so a section resolves to its
        -- verbatim text without re-running the layout reader.
        CREATE TABLE document_texts (
            revision_id       TEXT PRIMARY KEY REFERENCES document_revisions(revision_id),
            full_text         TEXT NOT NULL,
            char_count        INTEGER NOT NULL,
            page_count        INTEGER NOT NULL,
            extractor         TEXT NOT NULL DEFAULT '',
            extractor_version TEXT NOT NULL DEFAULT '',
            captured_at       TEXT NOT NULL DEFAULT '',
            org_id            TEXT NOT NULL DEFAULT 'default'
        );

        -- P1: a table row's cells, kept as cells. Flattening a requirements
        -- table loses which Measure belongs to which Part and which Applicable
        -- Systems row governs which requirement.
        CREATE TABLE source_table_cells (
            section_id   TEXT NOT NULL REFERENCES source_sections(section_id),
            row_index    INTEGER NOT NULL,
            col_index    INTEGER NOT NULL,
            column_name  TEXT NOT NULL DEFAULT '',
            text         TEXT NOT NULL DEFAULT '',
            org_id       TEXT NOT NULL DEFAULT 'default',
            PRIMARY KEY (section_id, row_index, col_index)
        );
        CREATE INDEX ix_source_table_cells_column ON source_table_cells(column_name);
        """,
    ),
    (
        12,
        "regulatory lifecycle on the revision (BILATERAL_CORPUS_V1 P3): the "
        "workbook's own retirement date, status and source URL",
        # NOTE: this runner splits statements on ';' -- never put one inside a
        # comment line inside a migration's SQL block (rule R9).
        """
        -- P3: the retirement boundary, parsed from the One-Stop-Shop workbook
        -- and never from a filename. NULL means the workbook states none, which
        -- is not the same as "never retires" and is not the same as unknown --
        -- the workbook cell is the fact either way.
        ALTER TABLE document_revisions ADD COLUMN inactive_date TEXT;

        -- P3: the workbook's own lifecycle status string, verbatim
        -- ('Mandatory Subject to Enforcement', 'Subject to Future
        -- Enforcement', 'Inactive'). Empty for a revision with no registry row.
        ALTER TABLE document_revisions ADD COLUMN lifecycle_status TEXT NOT NULL DEFAULT '';

        -- P3: where the bytes came from. Provenance for an acquired artifact,
        -- empty for one that arrived from disk.
        ALTER TABLE document_revisions ADD COLUMN source_url TEXT NOT NULL DEFAULT '';
        """,
    ),
    (
        13,
        "operator notes and the conversation corpus (BILATERAL_CORPUS_V1 P5/P6)",
        # NOTE: this runner splits statements on ';' -- never put one inside a
        # comment line inside a migration's SQL block (rule R9).
        """
        -- P5: an operator decision, intent or rationale, recorded as a dated and
        -- attributed source. The BODY lives where every other source's body
        -- lives -- a document revision and a section -- so a note is citeable,
        -- projectable and resolvable by exactly the same machinery. This table
        -- is the index over those notes by what they are ABOUT.
        CREATE TABLE operator_notes (
            note_id     TEXT PRIMARY KEY,
            subject_ref TEXT NOT NULL,
            kind        TEXT NOT NULL DEFAULT 'note',
            author      TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL,
            section_id  TEXT NOT NULL REFERENCES source_sections(section_id),
            revision_id TEXT NOT NULL REFERENCES document_revisions(revision_id),
            org_id      TEXT NOT NULL DEFAULT 'default'
        );
        CREATE INDEX ix_operator_notes_subject ON operator_notes(subject_ref);

        -- P6: an answer is one analyst's notes pinned to the revisions it read.
        -- Never a fact, never promoted by age, always outranked by a note.
        -- superseded_at is set when a revision it cited moves.
        CREATE TABLE conversation_answers (
            answer_id      TEXT PRIMARY KEY,
            thread_id      TEXT NOT NULL DEFAULT '',
            asked_at       TEXT NOT NULL,
            question       TEXT NOT NULL,
            answer         TEXT NOT NULL,
            model          TEXT NOT NULL DEFAULT '',
            subject_ref    TEXT NOT NULL DEFAULT '',
            elapsed_s      REAL NOT NULL DEFAULT 0,
            eval_count     INTEGER NOT NULL DEFAULT 0,
            prompt_bytes   INTEGER NOT NULL DEFAULT 0,
            load_duration_s REAL NOT NULL DEFAULT 0,
            reasoning_effort TEXT NOT NULL DEFAULT '',
            num_ctx        INTEGER NOT NULL DEFAULT 0,
            superseded_at  TEXT,
            superseded_by  TEXT NOT NULL DEFAULT '',
            correction_of  TEXT NOT NULL DEFAULT '',
            org_id         TEXT NOT NULL DEFAULT 'default'
        );
        CREATE INDEX ix_conversation_answers_subject ON conversation_answers(subject_ref);
        CREATE INDEX ix_conversation_answers_thread ON conversation_answers(thread_id);

        -- P6: every id an answer cited, with what it resolved to. An
        -- unresolvable citation is recorded as unresolvable rather than dropped.
        CREATE TABLE answer_citations (
            answer_id    TEXT NOT NULL REFERENCES conversation_answers(answer_id),
            cited_ref    TEXT NOT NULL,
            resolved     INTEGER NOT NULL DEFAULT 0,
            resolves_to  TEXT NOT NULL DEFAULT '',
            revision_id  TEXT NOT NULL DEFAULT '',
            jurisdiction TEXT NOT NULL DEFAULT '',
            source_kind  TEXT NOT NULL DEFAULT '',
            detail       TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (answer_id, cited_ref)
        );

        -- P6: the questions the operator already cares about. Run on ingest and
        -- on every auto-sync change -- that IS the initial assessment.
        CREATE TABLE standing_questions (
            question_id TEXT PRIMARY KEY,
            question    TEXT NOT NULL,
            subject_ref TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL,
            active      INTEGER NOT NULL DEFAULT 1,
            org_id      TEXT NOT NULL DEFAULT 'default'
        );
        """,
    ),
    (
        14,
        "requirement to section join, relation-typed (ONE_REGULATORY_EXTRACTION_V1 P2)",
        # NOTE: this runner splits statements on ';' -- never put one inside a
        # comment line inside a migration's SQL block (rule R9).
        """
        -- The key the graph and the corpus never shared. RegisterNode carries no
        -- section_id and source_sections carries no requirement reference, so the
        -- only overlap was source_pdf + source_pages, which is page granularity.
        -- requirement_anchor locates a requirement's verbatim_text in the captured
        -- character space by exact match and the overlapping sections ARE its
        -- sections. Those pairs land here.
        --
        -- relation is on the primary key because one section legitimately bears
        -- several relations to one requirement. A CIP requirements-table row is a
        -- single table_row unit whose text is the joined cells, so the requirement
        -- text, the applicable-systems column and the Measures column all sit in
        -- that one section. That is the normal case, not a collision.
        --
        -- Additive only. No source_sections row is written by any of this, so
        -- capture.assert_faithful is untouched.
        CREATE TABLE requirement_sections (
            requirement_id    TEXT NOT NULL,
            revision_id       TEXT NOT NULL REFERENCES document_revisions(revision_id),
            section_id        TEXT NOT NULL REFERENCES source_sections(section_id),
            relation          TEXT NOT NULL DEFAULT 'governing',
            char_start        INTEGER NOT NULL,
            char_end          INTEGER NOT NULL,
            occurrences       INTEGER NOT NULL DEFAULT 1,
            anchor_method     TEXT NOT NULL DEFAULT 'exact',
            anchored_at       TEXT NOT NULL,
            extractor_version TEXT NOT NULL DEFAULT '',
            org_id            TEXT NOT NULL DEFAULT 'default',
            PRIMARY KEY (requirement_id, revision_id, section_id, relation)
        );
        CREATE INDEX ix_requirement_sections_section ON requirement_sections(section_id);
        CREATE INDEX ix_requirement_sections_req ON requirement_sections(requirement_id, relation);

        -- An unanchored requirement is a queryable fact rather than a line in a
        -- report nobody re-reads. compliance_coverage reads this table.
        CREATE TABLE requirement_anchor_misses (
            requirement_id TEXT NOT NULL,
            revision_id    TEXT NOT NULL,
            relation       TEXT NOT NULL,
            reason         TEXT NOT NULL,
            anchored_at    TEXT NOT NULL,
            org_id         TEXT NOT NULL DEFAULT 'default',
            PRIMARY KEY (requirement_id, revision_id, relation)
        );
        """,
    ),
    (
        15,
        "the reading run and its receipt (BILATERAL_CORPUS_V1 P6.9)",
        # NOTE: this runner splits statements on ';' -- never put one inside a
        # comment line inside a migration's SQL block (rule R9).
        """
        -- What `conversation_answers` does NOT keep. That table retains the
        -- prose, the timing and the citations, which is enough to re-read an
        -- answer and not enough to audit one: the closure receipt, the scope it
        -- was computed over, the tool trace and the actual tool messages all
        -- lived in the returned payload and nowhere else, so a live reading's
        -- receipt was ephemeral by construction.
        --
        -- A run is retained whether or not the answer is projected into the
        -- corpus, and whether or not the reading FAILED -- a failed reading is
        -- the one most worth having a record of.
        CREATE TABLE reading_runs (
            run_id               TEXT PRIMARY KEY,
            answer_id            TEXT NOT NULL DEFAULT '',
            thread_id            TEXT NOT NULL DEFAULT '',
            asked_at             TEXT NOT NULL,
            subject_ref          TEXT NOT NULL,
            question             TEXT NOT NULL,
            answer               TEXT NOT NULL DEFAULT '',
            model                TEXT NOT NULL DEFAULT '',
            failed               INTEGER NOT NULL DEFAULT 0,
            failure              TEXT NOT NULL DEFAULT '',
            stop_reason          TEXT NOT NULL DEFAULT '',
            scope_json           TEXT NOT NULL DEFAULT '{}',
            closure_json         TEXT NOT NULL DEFAULT '{}',
            tool_trace_json      TEXT NOT NULL DEFAULT '[]',
            messages_json        TEXT NOT NULL DEFAULT '[]',
            verification_json    TEXT NOT NULL DEFAULT '{}',
            latency_json         TEXT NOT NULL DEFAULT '{}',
            context_fit_json     TEXT NOT NULL DEFAULT '{}',
            prompt_fingerprint   TEXT NOT NULL DEFAULT '',
            material_fingerprint TEXT NOT NULL DEFAULT '',
            revision_id          TEXT NOT NULL DEFAULT '',
            reasoning_effort     TEXT NOT NULL DEFAULT '',
            num_ctx              INTEGER NOT NULL DEFAULT 0,
            org_id               TEXT NOT NULL DEFAULT 'default'
        );
        CREATE INDEX ix_reading_runs_subject ON reading_runs(subject_ref, asked_at);
        CREATE INDEX ix_reading_runs_answer ON reading_runs(answer_id);
        CREATE INDEX ix_reading_runs_thread ON reading_runs(thread_id, asked_at);
        """,
    ),
    (
        16,
        "the prompt an answer was read under (PROVE_CIP_007_V1 P1.1)",
        # NOTE: this runner splits statements on ';' -- never put one inside a
        # comment line inside a migration's SQL block (rule R9).
        #
        # On an agentic reader the prompt is the primary lever, and it was a
        # hardcoded unversioned literal: the one input that left no trace on any
        # stored answer or receipt. A prompt change was therefore not
        # measurable, because there was nothing recorded to compare against.
        #
        # Two identifiers, not one. The declared version is what a person writes
        # in a report; the sha is of the prompt BODY, so an edited file carrying
        # an unchanged version string cannot pass as the same prompt.
        """
        ALTER TABLE conversation_answers ADD COLUMN prompt_version TEXT NOT NULL DEFAULT '';
        ALTER TABLE conversation_answers ADD COLUMN prompt_sha TEXT NOT NULL DEFAULT '';
        ALTER TABLE reading_runs ADD COLUMN prompt_version TEXT NOT NULL DEFAULT '';
        ALTER TABLE reading_runs ADD COLUMN prompt_sha TEXT NOT NULL DEFAULT '';
        """,
    ),
    (
        17,
        "machine_determined mapping status (PROVE_THEN_SCALE_V1 P2.1)",
        # A reading that examines both sides and says "this section implements
        # that Part, here is the text" writes an edge at its OWN status —
        # neither proposed (which reads like a candidate awaiting a human who
        # cannot get through 1,427 rows) nor ever approved (approved means a
        # human said so). requirement_scope.population keeps link_status, so a
        # population built from determined edges stays visibly different from
        # one built from approved ones.
        #
        # status carries a CHECK constraint, so the widened vocabulary needs a
        # table rebuild: create the successor with the expanded CHECK, copy
        # every row verbatim, drop, rename, restore the indexes. The rebuild
        # MUST name every column the preceding migrations added — base (1),
        # coverage trio (5), derivation (10). Naming only the base columns
        # compiles and runs and SILENTLY DROPS the rest; that mistake was made
        # on the live store, caught within minutes because
        # reading_assembly.linked_internal queries `derivation` and failed
        # loudly, and repaired by a forward migration plus a reconstruction of
        # the dropped values from the rationale/relation_type fingerprints the
        # original writers left (see reports/compliance/PROVE_THEN_SCALE_V1.md
        # §0-bis). Recorded here so the next table rebuild in this module
        # starts from the full column list, not the happy-path one.
        """
        CREATE TABLE relationship_assertions_new (
            assertion_id     TEXT PRIMARY KEY,
            relation_type    TEXT NOT NULL,
            src_ref          TEXT NOT NULL,
            src_revision_id  TEXT,
            dst_ref          TEXT NOT NULL,
            dst_revision_id  TEXT,
            scope            TEXT NOT NULL DEFAULT '',
            citations_json   TEXT NOT NULL DEFAULT '[]',
            status           TEXT NOT NULL DEFAULT 'proposed'
                             CHECK (status IN ('proposed','machine_determined','approved','rejected','revoked','stale')),
            review_state     TEXT NOT NULL DEFAULT 'proposed',
            valid_from       TEXT,
            valid_to         TEXT,
            recorded_from    TEXT NOT NULL,
            recorded_to      TEXT,
            rationale        TEXT NOT NULL DEFAULT '',
            decided_by       TEXT NOT NULL DEFAULT '',
            decided_at       TEXT,
            version          INTEGER NOT NULL DEFAULT 1,
            org_id           TEXT NOT NULL DEFAULT 'default',
            coverage         TEXT NOT NULL DEFAULT '',
            proposed_coverage TEXT NOT NULL DEFAULT '',
            confidence       REAL NOT NULL DEFAULT 0.0,
            derivation       TEXT NOT NULL DEFAULT ''
        );
        INSERT INTO relationship_assertions_new
            SELECT assertion_id, relation_type, src_ref, src_revision_id, dst_ref,
                   dst_revision_id, scope, citations_json, status, review_state,
                   valid_from, valid_to, recorded_from, recorded_to, rationale,
                   decided_by, decided_at, version, org_id,
                   coverage, proposed_coverage, confidence, derivation
            FROM relationship_assertions;
        DROP TABLE relationship_assertions;
        ALTER TABLE relationship_assertions_new RENAME TO relationship_assertions;
        CREATE INDEX ix_rel_src ON relationship_assertions(src_ref, status);
        CREATE INDEX ix_rel_dst ON relationship_assertions(dst_ref, status);
        """,
    ),
    (
        18,
        "the human-confirmed evaluation sample (PROVE_THEN_SCALE_V1 P5.3/P6)",
        # The module's founding property — settled mappings are human-owned and
        # double as the evaluation set — is circular once a machine determines
        # mappings at scale. The split: operational mappings (machine_determined
        # rows, never approved) build populations; THE EVALUATION SET is this
        # table — a small, stratified sample a human confirmed or corrected,
        # and the only thing the scorer is allowed to measure against. Sample
        # membership is recorded here rather than inferred from the assertion's
        # status, so approving a determined row during normal review can never
        # quietly induct it into the evaluation set.
        """
        CREATE TABLE evaluation_sample (
            sample_id        TEXT PRIMARY KEY,
            assertion_id     TEXT NOT NULL,
            requirement_id   TEXT NOT NULL,
            section_id       TEXT NOT NULL,
            relation_type    TEXT NOT NULL,
            machine_relation TEXT NOT NULL DEFAULT '',
            confidence       REAL NOT NULL DEFAULT 0.0,
            confidence_band  TEXT NOT NULL DEFAULT '',
            stratum_standard TEXT NOT NULL DEFAULT '',
            stratum_relation TEXT NOT NULL DEFAULT '',
            decision         TEXT NOT NULL DEFAULT '',
            human_relation   TEXT NOT NULL DEFAULT '',
            decided_by       TEXT NOT NULL DEFAULT '',
            decided_at       TEXT,
            notes            TEXT NOT NULL DEFAULT '',
            selected_at      TEXT NOT NULL,
            org_id           TEXT NOT NULL DEFAULT 'default'
        );
        CREATE INDEX ix_eval_sample_req ON evaluation_sample(requirement_id);
        CREATE INDEX ix_eval_sample_decision ON evaluation_sample(decision);
        """,
    ),
]
