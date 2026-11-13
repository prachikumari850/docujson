
def ensure_indexes(database):
    database.users.create_index(
        [("email_normalized", 1)],
        unique=True,
        name="uq_users_email",
    )

    database.organizations.create_index(
        [("slug", 1)],
        unique=True,
        name="uq_organizations_slug",
    )

    database.memberships.create_index(
        [("organization_id", 1), ("user_id", 1)],
        unique=True,
        name="uq_memberships_organization_user",
    )

    database.sessions.create_index(
        [("token_hash", 1)],
        unique=True,
        name="uq_sessions_token_hash",
    )

    database.sessions.create_index(
        [("expires_at", 1)],
        expireAfterSeconds=0,
        name="ttl_sessions_expires_at",
    )

    database.documents.create_index(
        [("organization_id", 1), ("conversion_id", 1)],
        unique=True,
        name="uq_documents_organization_conversion",
    )

    database.documents.create_index(
        [("organization_id", 1), ("created_at", -1)],
        name="ix_documents_organization_created",
    )

    database.processing_jobs.create_index(
        [("organization_id", 1), ("conversion_id", 1)],
        unique=True,
        name="uq_jobs_organization_conversion",
    )

    database.processing_jobs.create_index(
        [("organization_id", 1), ("status", 1), ("created_at", -1)],
        name="ix_jobs_organization_status_created",
    )

    database.questions.create_index(
        [
            ("organization_id", 1),
            ("conversion_id", 1),
            ("question_id", 1),
        ],
        unique=True,
        name="uq_questions_document_question",
    )

    database.questions.create_index(
        [
            ("organization_id", 1),
            ("question_type", 1),
            ("review_required", 1),
        ],
        name="ix_questions_organization_type_review",
    )

    database.answer_keys.create_index(
        [
            ("organization_id", 1),
            ("conversion_id", 1),
            ("entry_id", 1),
        ],
        unique=True,
        name="uq_answer_keys_document_entry",
    )

    database.answer_keys.create_index(
        [("organization_id", 1), ("status", 1)],
        name="ix_answer_keys_organization_status",
    )

    database.review_decisions.create_index(
        [
            ("organization_id", 1),
            ("entity_type", 1),
            ("entity_id", 1),
        ],
        unique=True,
        name="uq_review_decisions_entity",
    )

    database.publications.create_index(
        [
            ("organization_id", 1),
            ("conversion_id", 1),
            ("version", 1),
        ],
        unique=True,
        name="uq_publications_document_version",
    )

    database.publications.create_index(
        [("publication_id", 1)],
        unique=True,
        name="uq_publications_id",
    )

    database.publications.create_index(
        [("organization_id", 1), ("published_at", -1)],
        name="ix_publications_organization_date",
    )
