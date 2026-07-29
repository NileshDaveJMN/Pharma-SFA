# Generated manually to add InternalMessage.all_recipients

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('SFA', '0036_chemist_card_photo_chemist_owner_dob_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='internalmessage',
            name='all_recipients',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
    ]
