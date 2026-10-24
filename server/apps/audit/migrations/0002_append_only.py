"""The audit log is append-only in the database itself (E10-03): UPDATE and DELETE fail.

A trigger rather than REVOKE: the application connects as the table owner, and an owner keeps
its privileges. TRUNCATE (an administrative reset of a test database) is not covered.
"""

from django.db import migrations

FORBID = """
CREATE FUNCTION audit_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit log is append-only (%)', TG_OP USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER audit_auditevent_append_only
    BEFORE UPDATE OR DELETE ON audit_auditevent
    FOR EACH ROW EXECUTE FUNCTION audit_append_only();
"""

ALLOW = """
DROP TRIGGER IF EXISTS audit_auditevent_append_only ON audit_auditevent;
DROP FUNCTION IF EXISTS audit_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    operations = [migrations.RunSQL(FORBID, ALLOW)]
