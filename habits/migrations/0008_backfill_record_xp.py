from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('habits', '0007_habitrecord_xp_ledger'),
    ]

    operations = [
        # Con la lógica vieja, cada registro completado dio 25 (hábito) y 20 (global).
        migrations.RunSQL(
            sql="UPDATE habits_habitrecord SET xp_habit = 25, xp_global = 20 WHERE completed = TRUE;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]