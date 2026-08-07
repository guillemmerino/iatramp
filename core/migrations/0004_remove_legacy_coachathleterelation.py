from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_personclaiminvitation_personmergerecord_and_more"),
        ("iatrain", "0002_athleteprofile_coachprofile_coachathleterelation_and_more"),
    ]

    operations = [
        migrations.DeleteModel(name="CoachAthleteRelation"),
    ]
