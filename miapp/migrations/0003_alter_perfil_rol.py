# Generated by Django 5.1.1 on 2024-10-18 18:42

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('miapp', '0002_customuser_groups_customuser_is_superuser_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='perfil',
            name='rol',
            field=models.CharField(choices=[('dueño', 'Dueño'), ('trabajador', 'Trabajador'), ('administrador', 'Administrador')], default='dueño', max_length=20),
        ),
    ]
