# Hand-written migration (no shell available this session) adding optional
# gallery fields (up to 3 images + 1 video) to Faculty and Program, used by
# the shared media-carousel partial on faculty_detail.html / program_detail.html.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('eduweb', '0056_programsessioncreditcap'),
    ]

    operations = [
        migrations.AddField(
            model_name='faculty',
            name='gallery_image_1',
            field=models.ImageField(blank=True, help_text='Gallery image 1 (max 3MB)', null=True, upload_to='faculties/gallery/images/'),
        ),
        migrations.AddField(
            model_name='faculty',
            name='gallery_image_2',
            field=models.ImageField(blank=True, help_text='Gallery image 2 (max 3MB)', null=True, upload_to='faculties/gallery/images/'),
        ),
        migrations.AddField(
            model_name='faculty',
            name='gallery_image_3',
            field=models.ImageField(blank=True, help_text='Gallery image 3 (max 3MB)', null=True, upload_to='faculties/gallery/images/'),
        ),
        migrations.AddField(
            model_name='faculty',
            name='gallery_video',
            field=models.FileField(blank=True, help_text='Gallery video (shown first in carousel if present)', null=True, upload_to='faculties/gallery/videos/'),
        ),
        migrations.AddField(
            model_name='program',
            name='gallery_image_1',
            field=models.ImageField(blank=True, help_text='Gallery image 1 (max 3MB)', null=True, upload_to='programs/gallery/images/'),
        ),
        migrations.AddField(
            model_name='program',
            name='gallery_image_2',
            field=models.ImageField(blank=True, help_text='Gallery image 2 (max 3MB)', null=True, upload_to='programs/gallery/images/'),
        ),
        migrations.AddField(
            model_name='program',
            name='gallery_image_3',
            field=models.ImageField(blank=True, help_text='Gallery image 3 (max 3MB)', null=True, upload_to='programs/gallery/images/'),
        ),
        migrations.AddField(
            model_name='program',
            name='gallery_video',
            field=models.FileField(blank=True, help_text='Gallery video (shown first in carousel if present)', null=True, upload_to='programs/gallery/videos/'),
        ),
    ]
