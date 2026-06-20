from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('adminapp', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Staffs',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, blank=True, null=True)),
                ('role', models.CharField(max_length=100, blank=True, null=True)),
                ('specialization', models.CharField(max_length=255, blank=True, null=True)),
                ('phone', models.CharField(max_length=15, blank=True, null=True)),
                ('experience', models.CharField(max_length=50, blank=True, null=True)),
                ('joining_date', models.DateField(blank=True, null=True)),
                ('salary', models.DecimalField(max_digits=10, decimal_places=2, default=0)),
                ('status', models.CharField(max_length=10, default='Active')),
            ],
        ),
    ]