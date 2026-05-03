"""
Management command: seed_site_settings
Usage: python manage.py seed_site_settings

Seeds ONLY the site-settings-related tables:
  - ListOfCountry
  - SiteConfig
  - SiteHistoryMilestone
  - Testimonial
  - InstitutionMember
"""

from django.core.management.base import BaseCommand
from eduweb.models import (
    SiteConfig, SiteHistoryMilestone, InstitutionMember,
    Testimonial, ListOfCountry,
)

CAMPUS_MAP_EMBED = (
    '<iframe src="https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d3153.0!2d-122.419!3d37.774'
    '!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x0%3A0x0!2zMzfCsDQ2JzI2LjQiTiAxMjLCsDI1'
    'JzA4LjQiVw!5e0!3m2!1sen!2sus!4v1234567890" '
    'width="600" height="450" style="border:0;" allowfullscreen="" loading="lazy" '
    'referrerpolicy="no-referrer-when-downgrade"></iframe>'
)

PROMO_VIDEO_EMBED = (
    '<iframe width="560" height="315" src="https://www.youtube.com/embed/-mJFZp84TIY?si=GaHX9emFQiFb9uqa" '
    'title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; '
    'encrypted-media; gyroscope; picture-in-picture; web-share" '
    'referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>'
)


class Command(BaseCommand):
    help = 'Seeds site-settings tables: SiteConfig, milestones, testimonials, institution members, countries.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING('🌐 Seeding site settings...'))

        # ── CLEANUP ──────────────────────────────────────────────────────────
        self.stdout.write('🧹 Clearing existing site-settings data...')
        InstitutionMember.objects.all().delete()
        Testimonial.objects.all().delete()
        SiteHistoryMilestone.objects.all().delete()
        SiteConfig.objects.all().delete()
        ListOfCountry.objects.all().delete()
        self.stdout.write(self.style.SUCCESS('   ✅ Cleared'))

        # ── 1. COUNTRIES ─────────────────────────────────────────────────────
        self.stdout.write('🌍 Seeding countries...')
        country_data = [
            ('Nigeria',       'NG', '+234', 'Nigerian'),
            ('United States', 'US', '+1',   'American'),
            ('United Kingdom','GB', '+44',  'British'),
            ('Canada',        'CA', '+1',   'Canadian'),
            ('Germany',       'DE', '+49',  'German'),
            ('France',        'FR', '+33',  'French'),
            ('Australia',     'AU', '+61',  'Australian'),
            ('India',         'IN', '+91',  'Indian'),
            ('China',         'CN', '+86',  'Chinese'),
            ('Brazil',        'BR', '+55',  'Brazilian'),
            ('South Africa',  'ZA', '+27',  'South African'),
            ('Ghana',         'GH', '+233', 'Ghanaian'),
            ('Kenya',         'KE', '+254', 'Kenyan'),
            ('Singapore',     'SG', '+65',  'Singaporean'),
            ('Japan',         'JP', '+81',  'Japanese'),
            ('Mexico',        'MX', '+52',  'Mexican'),
            ('Italy',         'IT', '+39',  'Italian'),
            ('Spain',         'ES', '+34',  'Spanish'),
            ('Netherlands',   'NL', '+31',  'Dutch'),
            ('Sweden',        'SE', '+46',  'Swedish'),
        ]
        for country, code, phonecode, nationality in country_data:
            ListOfCountry.objects.get_or_create(
                country_code=code,
                defaults={
                    'country':          country,
                    'country_phonecode': phonecode,
                    'nationality':      nationality,
                }
            )
        self.stdout.write(self.style.SUCCESS(
            f'   ✅ {ListOfCountry.objects.count()} countries seeded'
        ))

        # ── 2. SITE CONFIG ────────────────────────────────────────────────────
        self.stdout.write('⚙️  Creating SiteConfig...')
        SiteConfig.objects.create(
            # Identity
            school_name='Melchisedec International University',
            school_short_name='MIU',
            tagline='The Best Learning Institution',
            theme_color='#840384',

            # Contact
            email='info@miu.edu',
            phone_primary='+1 (555) 123-4567',
            phone_secondary='+1 (555) 123-4568',
            phone_ng_primary='+234 801 234 5678',
            phone_ng_secondary='+234 802 345 6789',
            whatsapp='15551234567',

            # Addresses
            address_usa='123 University Avenue, Knowledge City, KC 10101, United States',
            address_nigeria='14 Academic Drive, Victoria Island, Lagos, Nigeria',

            # Social
            facebook='https://facebook.com/miu.edu',
            instagram='https://instagram.com/miu.edu',
            youtube='https://youtube.com/@miu_university',
            twitter='https://twitter.com/miu_edu',
            tiktok='https://tiktok.com/@miu.edu',
            linkedin='https://linkedin.com/school/melchisedec-international-university',

            # Labelled Emails
            email_admissions='admissions@miu.edu',
            email_info='info@miu.edu',
            email_international='international@miu.edu',

            # Labelled Phone Lines
            phone_admissions='+1 (555) 123-4567',
            phone_general='+1 (555) 123-4568',
            phone_international='+1 (555) 123-4569',

            # Office Hours
            office_hours_weekday='Monday - Friday: 8:00 AM - 6:00 PM',
            office_hours_saturday='Saturday: 9:00 AM - 1:00 PM',
            office_hours_sunday='Sunday: Closed',

            # Embeds
            promo_video_url=PROMO_VIDEO_EMBED,
            campus_map_embed_url=CAMPUS_MAP_EMBED,
            campus_map_address='123 University Avenue, Knowledge City, KC 10101',

            # Footer & SEO
            footer_tagline=(
                'Empowering global education since 1995 with innovative '
                'learning experiences and world-class faculty.'
            ),
            copyright_year='2025',
            meta_description=(
                'Melchisedec International University — world-class online and campus education '
                'across 50+ programs in 120+ countries since 1995.'
            ),
            meta_keywords='MIU, Melchisedec International University, online degrees, accredited programs',
        )
        self.stdout.write(self.style.SUCCESS('   ✅ SiteConfig created'))

        # ── 3. HISTORY MILESTONES ─────────────────────────────────────────────
        self.stdout.write('📜 Creating history milestones...')
        site_cfg = SiteConfig.objects.first()
        milestones = [
            (1995, 'Founding',
             'Melchisedec International University was established with a founding cohort of 120 '
             'students across three faculties.', 1),
            (2000, 'First Graduation',
             'Our inaugural graduating class of 47 students received their degrees at a ceremony '
             'attended by dignitaries from 12 countries.', 2),
            (2005, 'Online Campus Launch',
             'MIU became one of the first accredited institutions to offer fully online degree '
             'programmes, reaching students in 40+ countries.', 3),
            (2010, 'Research Excellence',
             'The university launched its flagship research centre, securing £4.2 m in grants '
             'during its first five years of operation.', 4),
            (2015, 'Global Expansion',
             'Partnership agreements signed with 30 universities worldwide, establishing student '
             'and faculty exchange programmes on five continents.', 5),
            (2020, 'Digital Transformation',
             'MIU transitioned its entire curriculum to a hybrid model, enabling uninterrupted '
             'learning through global disruptions.', 6),
            (2024, 'Accreditation Milestone',
             'Achieved triple accreditation, placing MIU among the top 2 % of universities '
             'worldwide for academic quality and governance.', 7),
        ]
        for year, title, desc, order in milestones:
            SiteHistoryMilestone.objects.create(
                site=site_cfg,
                year=year,
                title=title,
                description=desc,
                display_order=order,
                is_active=True,
            )
        self.stdout.write(self.style.SUCCESS(
            f'   ✅ {SiteHistoryMilestone.objects.count()} milestones created'
        ))

        # ── 4. TESTIMONIALS ───────────────────────────────────────────────────
        self.stdout.write('💬 Creating testimonials...')
        testimonial_data = [
            (
                "MIU's flexible online platform allowed me to complete my MBA while working "
                "full-time. The faculty support was exceptional, and I've already seen career "
                "advancement.",
                'Sarah K.', 'MBA Graduate, 2023', 1,
            ),
            (
                'The computer science program at MIU provided me with cutting-edge skills in AI '
                'and machine learning. I landed my dream job at a top tech company right after '
                'graduation.',
                'Michael Chen', 'Computer Science Graduate, 2024', 2,
            ),
            (
                'As an international student, I appreciated the global perspective and diverse '
                'community at MIU. The support services made my transition seamless and enriching.',
                'Amara O.', 'Health Sciences Graduate, 2023', 3,
            ),
            (
                'The engineering faculty at MIU is world-class. My lecturers brought real industry '
                'experience into every module. I graduated with confidence and a job offer in hand.',
                'James T.', 'Engineering Graduate, 2024', 4,
            ),
            (
                'Studying theology at MIU transformed my ministry. The blend of academic rigour '
                'and spiritual grounding is unlike anything I found elsewhere.',
                'Pastor Grace A.', 'Theology Graduate, 2022', 5,
            ),
        ]
        for quote, author_name, author_role, order in testimonial_data:
            Testimonial.objects.create(
                quote=quote,
                author_name=author_name,
                author_role=author_role,
                order=order,
                is_active=True,
            )
        self.stdout.write(self.style.SUCCESS(
            f'   ✅ {Testimonial.objects.count()} testimonials created'
        ))

        # ── 5. INSTITUTION MEMBERS ────────────────────────────────────────────
        self.stdout.write('👔 Creating institution members...')
        members = [
            # Admin / Management Board
            ('admin_board', 'Dr. Michael Rodriguez', 'University President', 0,
             'Former Dean of Harvard Graduate School of Education with 25+ years in academic leadership.'),
            ('admin_board', 'Dr. Sarah Chen', 'Provost & Chief Academic Officer', 1,
             'Expert in curriculum development and online education with a PhD from Stanford University.'),
            ('admin_board', 'Robert Johnson', 'Chair, Board of Trustees', 2,
             'Technology entrepreneur and philanthropist dedicated to educational innovation.'),
            ('admin_board', 'Dr. Amaka Okafor', 'Vice-Chancellor, Nigeria Campus', 3,
             'Leading academic administrator with expertise in African higher education systems.'),
            ('admin_board', 'Prof. David Williams', 'Director of Finance & Operations', 4,
             'Chartered accountant and finance director with 20 years in university management.'),
            # Academic Board
            ('academic_board', 'Prof. Alan Turing Jr.', 'Dean, Faculty of Computer Science & IT', 0,
             'Pioneer in artificial intelligence research and machine learning applications.'),
            ('academic_board', 'Dr. Grace Adeyemi', 'Dean, Faculty of Engineering', 1,
             'Civil engineer with a passion for sustainable infrastructure and green technology.'),
            ('academic_board', 'Prof. James Hargreaves', 'Dean, Faculty of Business & Management', 2,
             'Business strategist and former Fortune 500 executive turned academic leader.'),
            ('academic_board', 'Dr. Ngozi Eze', 'Dean, Faculty of Health Sciences', 3,
             'Registered nurse and public health expert with WHO consultancy experience.'),
            ('academic_board', 'Prof. Elena Vasquez', 'Dean, Faculty of Arts & Humanities', 4,
             'Literary scholar and cultural theorist with publications in 12 languages.'),
            # Advisorate Board
            ('advisorate_board', 'Sir Richard Blackwell', 'Senior Academic Advisor', 0,
             'Retired Oxford professor and Commonwealth education policy adviser.'),
            ('advisorate_board', 'Dr. Yuki Tanaka', 'International Relations Advisor', 1,
             'Specialist in cross-cultural academic partnerships across Asia-Pacific.'),
            ('advisorate_board', 'Ms. Fatima Al-Hassan', 'Diversity & Inclusion Advisor', 2,
             'Advocate for inclusive education and women in STEM programmes globally.'),
            # Staff
            ('staff', 'Mr. Emeka Nwosu', 'Head of Admissions', 0,
             'Coordinates all domestic and international student admissions processes.'),
            ('staff', 'Ms. Lisa Okonkwo', 'Head of Student Services', 1,
             'Oversees student welfare, accommodation, and academic support services.'),
            ('staff', 'Mr. Paul Mensah', 'IT Systems Administrator', 2,
             'Manages university digital infrastructure and e-learning platforms.'),
        ]
        for mtype, name, role, order, bio in members:
            InstitutionMember.objects.create(
                member_type=mtype,
                name=name,
                role=role,
                bio=bio,
                display_order=order,
                is_active=True,
            )
        self.stdout.write(self.style.SUCCESS(
            f'   ✅ {InstitutionMember.objects.count()} institution members created'
        ))

        # ── SUMMARY ───────────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 55))
        self.stdout.write(self.style.SUCCESS('✅  SITE SETTINGS SEEDING COMPLETE'))
        self.stdout.write(self.style.SUCCESS('=' * 55))
        rows = [
            ('Countries',            ListOfCountry.objects.count()),
            ('SiteConfig',           SiteConfig.objects.count()),
            ('History Milestones',   SiteHistoryMilestone.objects.count()),
            ('Testimonials',         Testimonial.objects.count()),
            ('Institution Members',  InstitutionMember.objects.count()),
        ]
        for label, count in rows:
            self.stdout.write(f'   {label:<28} {count}')
        self.stdout.write(self.style.SUCCESS('=' * 55 + '\n'))