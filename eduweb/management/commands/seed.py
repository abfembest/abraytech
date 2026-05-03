import random
import uuid
from decimal import Decimal
from datetime import timedelta, date
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from faker import Faker

from eduweb.models import (
    SiteConfig, SiteHistoryMilestone, InstitutionMember, Testimonial,
    Announcement, Assignment, AssignmentSubmission, AuditLog, Badge, StudentBadge,
    BlogCategory, BlogPost, Certificate, ContactMessage,
    Faculty, Department, Program, Course, AcademicSession, AllRequiredPayments,
    CourseIntake, CourseApplication, ApplicationDocument, ApplicationPayment,
    CourseCategory, Discussion, DiscussionReply, Enrollment, SupportTicket,
    TicketReply, Invoice, LessonProgress, LMSCourse, Lesson, LessonSection,
    Message, Notification, PaymentGateway, Transaction, Quiz, QuizQuestion,
    QuizAnswer, QuizAttempt, QuizResponse, Review, SubscriptionPlan,
    Subscription, SystemConfiguration, UserProfile, Vendor, StudyGroup,
    StudyGroupMember, StudyGroupMessage, BroadcastMessage, StaffPayroll,
    ListOfCountry, FeePayment, CourseRegistration, CourseGrade, LibraryItem,
    Exam, ExamQuestion, StudentExamResponse, ExamStatusLog,
)

fake = Faker()

# ── Provided embed codes (iframe strings) for lesson video_url fields ──────────
EMBED_CODES = [
    '<iframe width="560" height="315" src="https://www.youtube.com/embed/-mJFZp84TIY?si=GaHX9emFQiFb9uqa" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>',
    '<iframe width="560" height="315" src="https://www.youtube.com/embed/hnVOvvbQrwA?si=dGpgO4TTbiodxWwl" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>',
    '<iframe width="560" height="315" src="https://www.youtube.com/embed/kFe-RRaOy48?si=8ckGG-v-_Ne3G_rX" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>',
    '<iframe width="560" height="315" src="https://www.youtube.com/embed/JvC7aA24m4Q?si=CHCpJvjlj7NR1hcp" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>',
    '<iframe width="560" height="315" src="https://www.youtube.com/embed/wa0IVAIqbo0?si=7IPmWFuHJm3_r-KX" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>',
    '<blockquote class="tiktok-embed" cite="https://www.tiktok.com/@adjacentnode/video/7599691161455971615" data-video-id="7599691161455971615" style="max-width: 605px;min-width: 325px;" > <section> <a target="_blank" title="@adjacentnode" href="https://www.tiktok.com/@adjacentnode?refer=embed">@adjacentnode</a> Can you answer this entry level networking job interview question? <a title="tech" target="_blank" href="https://www.tiktok.com/tag/tech?refer=embed">#tech</a> <a title="networking" target="_blank" href="https://www.tiktok.com/tag/networking?refer=embed">#networking</a> <a target="_blank" title="♬ original sound - Kevin Nanns" href="https://www.tiktok.com/music/original-sound-7599691216300591902?refer=embed">♬ original sound - Kevin Nanns</a> </section> </blockquote> <script async src="https://www.tiktok.com/embed.js"></script>',
    '<blockquote class="tiktok-embed" cite="https://www.tiktok.com/@clickconsulting/video/7539746341270998280" data-video-id="7539746341270998280" style="max-width: 605px;min-width: 325px;" > <section> <a target="_blank" title="@clickconsulting" href="https://www.tiktok.com/@clickconsulting?refer=embed">@clickconsulting</a> Network Rack 101 <a title="it" target="_blank" href="https://www.tiktok.com/tag/it?refer=embed">#IT</a> <a title="learnontiktok" target="_blank" href="https://www.tiktok.com/tag/learnontiktok?refer=embed">#learnontiktok</a> <a target="_blank" title="♬ original sound - Click Consulting" href="https://www.tiktok.com/music/original-sound-7539746534930303745?refer=embed">♬ original sound - Click Consulting</a> </section> </blockquote> <script async src="https://www.tiktok.com/embed.js"></script>',
]

CAMPUS_MAP_EMBED = (
    '<iframe src="https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d3153.0!2d-122.419!3d37.774!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x0%3A0x0!2zMzfCsDQ2JzI2LjQiTiAxMjLCsDI1JzA4LjQiVw!5e0!3m2!1sen!2sus!4v1234567890" '
    'width="600" height="450" style="border:0;" allowfullscreen="" loading="lazy" referrerpolicy="no-referrer-when-downgrade"></iframe>'
)

PROMO_VIDEO_EMBED = (
    '<iframe width="560" height="315" src="https://www.youtube.com/embed/-mJFZp84TIY?si=GaHX9emFQiFb9uqa" '
    'title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; '
    'encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" '
    'allowfullscreen></iframe>'
)


class Command(BaseCommand):
    help = 'Seeds ALL tables with realistic data covering every single field'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING(
            "🚀 Starting FULL database seeding — every table, every field..."
        ))

        # ── CLEANUP ──────────────────────────────────────────────────────────
        self.stdout.write("🧹 Clearing existing data...")
        models_to_clear = [
            ExamStatusLog, StudentExamResponse, ExamQuestion, Exam,
            CourseGrade, CourseRegistration, LibraryItem,
            AuditLog, Notification, Message, TicketReply, SupportTicket,
            StudentBadge, Badge, QuizResponse, QuizAttempt, QuizAnswer,
            QuizQuestion, Quiz, AssignmentSubmission, Assignment,
            LessonProgress, Certificate, Review, Enrollment, DiscussionReply,
            Discussion, Lesson, LessonSection, LMSCourse, CourseCategory,
            ApplicationPayment, ApplicationDocument, CourseApplication,
            CourseIntake, AllRequiredPayments, StaffPayroll,
            Course, AcademicSession, Program, Department, Faculty,
            Invoice, Transaction, Subscription, SubscriptionPlan,
            PaymentGateway, BlogPost, BlogCategory, ContactMessage,
            Vendor, SystemConfiguration, Announcement,
            StudyGroupMessage, StudyGroupMember, StudyGroup, BroadcastMessage,
            InstitutionMember, SiteHistoryMilestone, SiteConfig, Testimonial, ListOfCountry,
        ]
        for model in models_to_clear:
            model.objects.all().delete()
        UserProfile.objects.all().delete()
        User.objects.all().delete()
        self.stdout.write(self.style.SUCCESS("   ✅ All data cleared"))

        # ── 0. LIST OF COUNTRIES ─────────────────────────────────────────────
        self.stdout.write("🌍 Seeding countries...")
        country_data = [
            ('Nigeria', 'NG', '+234', 'Nigerian'),
            ('United States', 'US', '+1', 'American'),
            ('United Kingdom', 'GB', '+44', 'British'),
            ('Canada', 'CA', '+1', 'Canadian'),
            ('Germany', 'DE', '+49', 'German'),
            ('France', 'FR', '+33', 'French'),
            ('Australia', 'AU', '+61', 'Australian'),
            ('India', 'IN', '+91', 'Indian'),
            ('China', 'CN', '+86', 'Chinese'),
            ('Brazil', 'BR', '+55', 'Brazilian'),
            ('South Africa', 'ZA', '+27', 'South African'),
            ('Ghana', 'GH', '+233', 'Ghanaian'),
            ('Kenya', 'KE', '+254', 'Kenyan'),
            ('Singapore', 'SG', '+65', 'Singaporean'),
            ('Japan', 'JP', '+81', 'Japanese'),
            ('Mexico', 'MX', '+52', 'Mexican'),
            ('Italy', 'IT', '+39', 'Italian'),
            ('Spain', 'ES', '+34', 'Spanish'),
            ('Netherlands', 'NL', '+31', 'Dutch'),
            ('Sweden', 'SE', '+46', 'Swedish'),
        ]
        for country, code, phonecode, nationality in country_data:
            ListOfCountry.objects.get_or_create(
                country_code=code,
                defaults={
                    'country': country,
                    'country_phonecode': phonecode,
                    'nationality': nationality,
                }
            )
        self.stdout.write(self.style.SUCCESS(f"   ✅ {ListOfCountry.objects.count()} countries seeded"))

        # ── 1. SITE CONFIG ───────────────────────────────────────────────────
        self.stdout.write("🌐 Creating site configuration...")
        SiteConfig.objects.create(
            # ── Identity ──────────────────────────────────────────────────────
            school_name='Melchisedec International University',
            school_short_name='MIU',
            tagline='The Best Learning Institution',
            theme_color='#840384',
            # logo / logo_dark / favicon / og_image left blank (no image files to reference)

            # ── Contact ───────────────────────────────────────────────────────
            email='info@miu.edu',
            phone_primary='+1 (555) 123-4567',
            phone_secondary='+1 (555) 123-4568',
            phone_ng_primary='+234 801 234 5678',
            phone_ng_secondary='+234 802 345 6789',
            whatsapp='15551234567',

            # ── Addresses ─────────────────────────────────────────────────────
            address_usa='123 University Avenue, Knowledge City, KC 10101, United States',
            address_nigeria='14 Academic Drive, Victoria Island, Lagos, Nigeria',

            # ── Social ────────────────────────────────────────────────────────
            facebook='https://facebook.com/miu.edu',
            instagram='https://instagram.com/miu.edu',
            youtube='https://youtube.com/@miu_university',
            twitter='https://twitter.com/miu_edu',
            tiktok='https://tiktok.com/@miu.edu',
            linkedin='https://linkedin.com/school/melchisedec-international-university',

            # ── Labelled Emails ───────────────────────────────────────────────
            email_admissions='admissions@miu.edu',
            email_info='info@miu.edu',
            email_international='international@miu.edu',

            # ── Labelled Phone Lines ──────────────────────────────────────────
            phone_admissions='+1 (555) 123-4567',
            phone_general='+1 (555) 123-4568',
            phone_international='+1 (555) 123-4569',

            # ── Office Hours ──────────────────────────────────────────────────
            office_hours_weekday='Monday - Friday: 8:00 AM - 6:00 PM',
            office_hours_saturday='Saturday: 9:00 AM - 1:00 PM',
            office_hours_sunday='Sunday: Closed',

            # ── Embed Codes ───────────────────────────────────────────────────
            promo_video_url=PROMO_VIDEO_EMBED,
            campus_map_embed_url=CAMPUS_MAP_EMBED,
            campus_map_address='123 University Avenue, Knowledge City, KC 10101',
            # virtual_tour_url left blank (no embed code to reference)

            # ── Footer & SEO ──────────────────────────────────────────────────
            footer_tagline='Empowering global education since 1995 with innovative learning experiences and world-class faculty.',
            copyright_year='2025',
            meta_description=(
                'Melchisedec International University — world-class online and campus education '
                'across 50+ programs in 120+ countries since 1995.'
            ),
            meta_keywords='MIU, Melchisedec International University, online degrees, accredited programs',
        )
        self.stdout.write(self.style.SUCCESS("   ✅ SiteConfig created"))

        # ── 1a. HISTORY MILESTONES ────────────────────────────────────────────
        self.stdout.write("📜 Creating history milestones...")
        site_cfg = SiteConfig.objects.first()
        milestones = [
            (1995, 'Founding',             'Melchisedec International University was established with a founding cohort of 120 students across three faculties.', 1),
            (2000, 'First Graduation',     'Our inaugural graduating class of 47 students received their degrees at a ceremony attended by dignitaries from 12 countries.', 2),
            (2005, 'Online Campus Launch', 'MIU became one of the first accredited institutions to offer fully online degree programmes, reaching students in 40+ countries.', 3),
            (2010, 'Research Excellence',  'The university launched its flagship research centre, securing £4.2 m in grants during its first five years of operation.', 4),
            (2015, 'Global Expansion',     'Partnership agreements signed with 30 universities worldwide, establishing student and faculty exchange programmes on five continents.', 5),
            (2020, 'Digital Transformation', 'MIU transitioned its entire curriculum to a hybrid model, enabling uninterrupted learning through global disruptions.', 6),
            (2024, 'Accreditation Milestone', 'Achieved triple accreditation, placing MIU among the top 2 % of universities worldwide for academic quality and governance.', 7),
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
        self.stdout.write(self.style.SUCCESS(f"   ✅ {SiteHistoryMilestone.objects.count()} history milestones created"))

        # ── 1b. TESTIMONIALS ─────────────────────────────────────────────────
        self.stdout.write("💬 Creating testimonials...")
        testimonial_data = [
            (
                "MIU's flexible online platform allowed me to complete my MBA while working full-time. "
                "The faculty support was exceptional, and I've already seen career advancement.",
                'Sarah K.', 'MBA Graduate, 2023', 1,
            ),
            (
                'The computer science program at MIU provided me with cutting-edge skills in AI and '
                'machine learning. I landed my dream job at a top tech company right after graduation.',
                'Michael Chen', 'Computer Science Graduate, 2024', 2,
            ),
            (
                'As an international student, I appreciated the global perspective and diverse community '
                'at MIU. The support services made my transition seamless and enriching.',
                'Amara O.', 'Health Sciences Graduate, 2023', 3,
            ),
            (
                'The engineering faculty at MIU is world-class. My lecturers brought real industry '
                'experience into every module. I graduated with confidence and a job offer in hand.',
                'James T.', 'Engineering Graduate, 2024', 4,
            ),
            (
                'Studying theology at MIU transformed my ministry. The blend of academic rigour and '
                'spiritual grounding is unlike anything I found elsewhere.',
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
        self.stdout.write(self.style.SUCCESS(f"   ✅ {Testimonial.objects.count()} testimonials created"))

        # ── 2. INSTITUTION MEMBERS ───────────────────────────────────────────
        self.stdout.write("👔 Creating institution members...")
        institution_members_data = [
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
        for mtype, name, role, order, bio in institution_members_data:
            InstitutionMember.objects.create(
                member_type=mtype,
                name=name,
                role=role,
                bio=bio,
                display_order=order,
                is_active=True,
            )
        self.stdout.write(self.style.SUCCESS(f"   ✅ {InstitutionMember.objects.count()} institution members created"))

        # ── 3. USERS ─────────────────────────────────────────────────────────
        self.stdout.write("👥 Creating users...")
        users = {
            'students': [], 'instructors': [], 'admins': [],
            'support': [], 'content_managers': [], 'finance': [], 'qa': [],
        }

        def make_users(username_prefix, role_key, count=6, is_staff=False):
            created = []
            for i in range(count):
                uname = f"{username_prefix}{i + 1}" if i > 0 else username_prefix
                u = User.objects.create_user(
                    username=uname,
                    email=f"{uname}@miu.edu",
                    password="12345",
                    first_name=fake.first_name(),
                    last_name=fake.last_name(),
                    is_staff=is_staff,
                )
                p = u.profile
                p.role = role_key
                p.bio = fake.text(max_nb_chars=250)
                p.phone = fake.phone_number()[:20]
                p.date_of_birth = fake.date_of_birth(minimum_age=22, maximum_age=55)
                p.address = fake.street_address()
                p.city = fake.city()
                p.country = fake.country()
                p.website = fake.url() if random.random() > 0.5 else ''
                p.linkedin = f"https://linkedin.com/in/{uname}"
                p.twitter = f"https://twitter.com/{uname}" if random.random() > 0.5 else ''
                p.email_notifications = random.choice([True, False])
                p.marketing_emails = random.choice([True, False])
                p.email_verified = i < 4
                # academic progression — set after sessions exist; patched below
                p.year_of_study = 1
                p.progression_status = 'active'
                p.save()
                created.append(u)
            return created

        users['students'] = make_users('student', 'student', 8)
        users['instructors'] = make_users('instructor', 'instructor', 6)
        users['admins'] = make_users('admin', 'admin', 4, is_staff=True)
        users['content_managers'] = make_users('content_mgr', 'content_manager', 4)
        users['support'] = make_users('support', 'support', 4)
        users['finance'] = make_users('finance', 'finance', 4)
        users['qa'] = make_users('qa', 'qa', 4)

        all_users = sum(users.values(), [])
        verified_students = [u for u in users['students'] if u.profile.email_verified]
        verified_instructors = [u for u in users['instructors'] if u.profile.email_verified]
        verified_admins = [u for u in users['admins'] if u.profile.email_verified]
        verified_support = [u for u in users['support'] if u.profile.email_verified]
        verified_finance = [u for u in users['finance'] if u.profile.email_verified]
        verified_content = [u for u in users['content_managers'] if u.profile.email_verified]
        verified_all = [u for u in all_users if u.profile.email_verified]
        staff_users = (
            users['instructors'] + users['admins'] +
            users['support'] + users['finance'] + users['content_managers']
        )
        self.stdout.write(self.style.SUCCESS(f"   ✅ {len(all_users)} users created"))

        # ── 4. VENDORS ───────────────────────────────────────────────────────
        self.stdout.write("🏢 Creating vendors...")
        vendors = []
        for vd in [
            ('Tech University Partners', 'United States'),
            ('Global Education Alliance', 'United Kingdom'),
            ('Asian Institute Network', 'Singapore'),
            ('European Learning Consortium', 'Germany'),
            ('Australian Education Hub', 'Australia'),
        ]:
            vendors.append(Vendor.objects.create(
                name=vd[0],
                email=fake.company_email(),
                country=vd[1],
                stripe_account_id=f"acct_{uuid.uuid4().hex[:16]}",
                is_active=True,
            ))

        # ── 5. SYSTEM CONFIGURATIONS ─────────────────────────────────────────
        self.stdout.write("⚙️  Creating system configurations...")
        cfg_data = [
            ('site_name', 'MIU Learning Platform', 'text', True),
            ('max_upload_size', '10485760', 'number', False),
            ('email_notifications_enabled', 'true', 'boolean', True),
            ('maintenance_mode', 'false', 'boolean', False),
            ('default_currency', 'USD', 'text', True),
            ('max_enrollments_per_user', '50', 'number', False),
            ('certificate_enabled', 'true', 'boolean', True),
            ('forum_enabled', 'true', 'boolean', True),
            ('registration_open', 'true', 'boolean', True),
            ('smtp_host', 'smtp.gmail.com', 'text', False),
        ]
        cfg_editors = users['admins'] + users['content_managers']
        for key, val, stype, is_pub in cfg_data:
            SystemConfiguration.objects.create(
                key=key, value=val, setting_type=stype,
                description=f"Controls {key.replace('_', ' ')}",
                is_public=is_pub,
                updated_by=random.choice(cfg_editors),
            )

        # ── 6. PAYMENT GATEWAYS ──────────────────────────────────────────────
        self.stdout.write("💳 Creating payment gateways...")
        gateways = []
        for name, slug, gtype, active in [
            ('Stripe', 'stripe', 'stripe', True),
            ('PayPal', 'paypal', 'paypal', True),
            ('Razorpay', 'razorpay', 'razorpay', False),
        ]:
            gateways.append(PaymentGateway.objects.create(
                name=name, slug=slug, gateway_type=gtype,
                api_key=f"pk_test_{uuid.uuid4().hex}",
                api_secret=f"sk_test_{uuid.uuid4().hex}",
                webhook_secret=f"whsec_{uuid.uuid4().hex}",
                is_active=active, is_test_mode=True,
            ))

        # ── 7. SUBSCRIPTION PLANS ────────────────────────────────────────────
        self.stdout.write("📋 Creating subscription plans...")
        plans = []
        plan_data = [
            ('Free', 'Access to free courses only', Decimal('0.00'), 'yearly',
             ['Free courses', 'Community forums', 'Basic support'], 5, False),
            ('Basic', 'Perfect for individual learners', Decimal('29.99'), 'monthly',
             ['All free features', 'Premium courses', 'Email support', 'Downloadable resources'], 20, False),
            ('Pro', 'Best value for serious learners', Decimal('79.99'), 'monthly',
             ['All Basic features', 'Unlimited courses', 'Priority support', 'Certificates', 'Live Q&A'], None, True),
            ('Enterprise', 'For teams and organisations', Decimal('299.99'), 'monthly',
             ['All Pro features', 'Team management', 'Custom branding', 'Dedicated support', 'API access'], None, False),
        ]
        for idx, (name, desc, price, cycle, features, max_c, popular) in enumerate(plan_data):
            plans.append(SubscriptionPlan.objects.create(
                name=name, description=desc, price=price, currency='USD',
                billing_cycle=cycle, features=features,
                max_courses=max_c, is_active=True,
                is_popular=popular, display_order=idx,
            ))

        # ── 8. SUBSCRIPTIONS ─────────────────────────────────────────────────
        self.stdout.write("🎫 Creating subscriptions...")
        for student in verified_students:
            plan = random.choice(plans)
            days = 30 if plan.billing_cycle == 'monthly' else 365
            start = timezone.now().date() - timedelta(days=random.randint(0, 60))
            status = random.choice(['active', 'active', 'active', 'cancelled', 'expired'])
            Subscription.objects.create(
                user=student, plan=plan, status=status,
                end_date=start + timedelta(days=days),
                auto_renew=random.choice([True, False]),
                gateway_subscription_id=f"sub_{uuid.uuid4().hex[:24]}",
                cancelled_at=timezone.now() - timedelta(days=random.randint(1, 20))
                if status == 'cancelled' else None,
            )

        # ── 9. FACULTIES ─────────────────────────────────────────────────────
        self.stdout.write("🎓 Creating faculties...")
        faculty_raw = [
            {
                'name': 'Faculty of Computer Science & IT', 'code': 'CSIT',
                'icon': 'cpu', 'color_primary': 'blue', 'color_secondary': 'cyan',
                'tagline': 'Leading the digital revolution',
                'description': 'Leading education in computing, software development, and IT.',
                'mission': 'To produce world-class graduates equipped with cutting-edge technology skills.',
                'vision': 'To be a globally recognised centre of excellence in computing.',
                'accreditation': 'Accredited by British Computer Society (BCS) – 2023',
                'student_count': 1850, 'placement_rate': 94,
                'partner_count': 42, 'international_faculty': 35,
                'special_features': [
                    'State-of-the-art AI & Robotics Lab',
                    'Industry partnerships with Google, Microsoft, Amazon',
                    'International exchange programmes with MIT and Oxford',
                    'Annual Hackathon with $50K prize pool',
                ],
                'dean_name': 'Prof. Alan Turing Jr.',
                'dean_role': 'Dean',
                'dean_faculty_label': 'Faculty of Computer Science & IT',
            },
            {
                'name': 'Faculty of Engineering', 'code': 'ENG',
                'icon': 'cog', 'color_primary': 'orange', 'color_secondary': 'amber',
                'tagline': 'Building tomorrow, today',
                'description': 'Excellence in engineering education across multiple disciplines.',
                'mission': 'Develop innovative engineers who solve real-world challenges.',
                'vision': 'A faculty synonymous with engineering excellence and industry impact.',
                'accreditation': 'Accredited by Institution of Engineering and Technology (IET) – 2022',
                'student_count': 1420, 'placement_rate': 91,
                'partner_count': 38, 'international_faculty': 28,
                'special_features': [
                    'Fully equipped civil and structural testing lab',
                    'Partnerships with Arup, Atkins, and Balfour Beatty',
                    'Year in industry placement scheme',
                    'Research collaborations with national infrastructure bodies',
                ],
                'dean_name': 'Dr. Grace Adeyemi',
                'dean_role': 'Dean',
                'dean_faculty_label': 'Faculty of Engineering',
            },
            {
                'name': 'Faculty of Business & Management', 'code': 'BUS',
                'icon': 'briefcase', 'color_primary': 'green', 'color_secondary': 'emerald',
                'tagline': 'Shaping future leaders',
                'description': 'Preparing future business leaders and entrepreneurs.',
                'mission': 'Develop principled leaders who create sustainable value.',
                'vision': 'A globally ranked business faculty producing transformational leaders.',
                'accreditation': 'AACSB Accredited – 2021',
                'student_count': 2200, 'placement_rate': 89,
                'partner_count': 55, 'international_faculty': 40,
                'special_features': [
                    'Bloomberg Terminal Lab', 'Executive mentorship programme',
                    'Annual Business Plan Competition',
                    'Global study trips to New York, Singapore, and Dubai',
                ],
                'dean_name': 'Prof. James Hargreaves',
                'dean_role': 'Dean',
                'dean_faculty_label': 'Faculty of Business & Management',
            },
            {
                'name': 'Faculty of Health Sciences', 'code': 'HLTH',
                'icon': 'heart', 'color_primary': 'red', 'color_secondary': 'rose',
                'tagline': 'Caring for tomorrow',
                'description': 'Comprehensive health education and clinical training.',
                'mission': 'Produce compassionate, competent healthcare professionals.',
                'vision': 'Leading faculty for health sciences education in the region.',
                'accreditation': 'Accredited by Nursing and Midwifery Council (NMC) – 2023',
                'student_count': 980, 'placement_rate': 97,
                'partner_count': 25, 'international_faculty': 20,
                'special_features': [
                    'Simulation wards and high-fidelity clinical mannequins',
                    'NHS Trust placement partnerships',
                    'Interprofessional education programme',
                    'Research links with WHO and Public Health England',
                ],
                'dean_name': 'Dr. Ngozi Eze',
                'dean_role': 'Dean',
                'dean_faculty_label': 'Faculty of Health Sciences',
            },
            {
                'name': 'Faculty of Arts & Humanities', 'code': 'ART',
                'icon': 'palette', 'color_primary': 'purple', 'color_secondary': 'violet',
                'tagline': 'Inspiring creativity and critical thinking',
                'description': 'Fostering creativity and critical thinking in arts and humanities.',
                'mission': 'Nurture creative minds and independent critical thinkers.',
                'vision': 'A faculty that bridges creativity, culture, and commerce.',
                'accreditation': 'Quality Assurance Agency (QAA) Reviewed – 2022',
                'student_count': 1100, 'placement_rate': 82,
                'partner_count': 30, 'international_faculty': 22,
                'special_features': [
                    'Modern art studios and digital design suites',
                    'Annual Arts Festival', 'Partnerships with national museums',
                    'Study abroad links with Sorbonne and Florence Academy',
                ],
                'dean_name': 'Prof. Elena Vasquez',
                'dean_role': 'Dean',
                'dean_faculty_label': 'Faculty of Arts & Humanities',
            },
        ]
        faculties = []
        for idx, fd in enumerate(faculty_raw):
            f = Faculty.objects.create(
                name=fd['name'], code=fd['code'],
                icon=fd['icon'],
                color_primary=fd['color_primary'],
                color_secondary=fd['color_secondary'],
                tagline=fd['tagline'],
                description=fd['description'],
                mission=fd['mission'],
                vision=fd['vision'],
                dean_name=fd['dean_name'],
                dean_role=fd['dean_role'],
                dean_faculty_label=fd['dean_faculty_label'],
                accreditation=fd['accreditation'],
                student_count=fd['student_count'],
                placement_rate=fd['placement_rate'],
                partner_count=fd['partner_count'],
                international_faculty=fd['international_faculty'],
                special_features=fd['special_features'],
                meta_description=fd['description'][:160],
                meta_keywords=f"{fd['name']}, university, degree, {fd['code']}",
                is_active=True, display_order=idx,
            )
            faculties.append(f)

        # ── 10. DEPARTMENTS ──────────────────────────────────────────────────
        self.stdout.write("🏛️  Creating departments...")
        dept_raw = [
            (faculties[0], 'Department of Software Engineering', 'SE',
             'Focuses on design, development, and maintenance of software systems.', 0),
            (faculties[0], 'Department of Artificial Intelligence', 'AI',
             'Research and teaching at the frontier of AI and machine learning.', 1),
            (faculties[0], 'Department of Cybersecurity', 'CYS',
             'Specialists in network security, ethical hacking, and digital forensics.', 2),
            (faculties[1], 'Department of Civil Engineering', 'CVE',
             'Structural design, environmental systems, and infrastructure engineering.', 0),
            (faculties[1], 'Department of Electrical Engineering', 'EEE',
             'Power systems, electronics, and telecommunications engineering.', 1),
            (faculties[1], 'Department of Mechanical Engineering', 'MEE',
             'Thermodynamics, manufacturing, and mechanical design.', 2),
            (faculties[2], 'Department of Finance & Accounting', 'FNA',
             'Financial analysis, corporate finance, and accounting standards.', 0),
            (faculties[2], 'Department of Marketing & Strategy', 'MKS',
             'Brand management, consumer behaviour, and corporate strategy.', 1),
            (faculties[2], 'Department of Entrepreneurship', 'ENT',
             'Startup ecosystems, innovation management, and venture creation.', 2),
            (faculties[3], 'Department of Nursing', 'NRS',
             'Adult, child, and mental health nursing education and practice.', 0),
            (faculties[3], 'Department of Public Health', 'PHE',
             'Epidemiology, health policy, and community health management.', 1),
            (faculties[4], 'Department of English & Creative Writing', 'ECW',
             'Literature, linguistics, and creative and professional writing.', 0),
            (faculties[4], 'Department of Digital Media & Design', 'DMD',
             'Graphic design, multimedia production, and digital arts.', 1),
        ]
        departments = []
        for fac, name, code, desc, order in dept_raw:
            d = Department.objects.create(
                faculty=fac, name=name, code=code,
                description=desc, is_active=True, display_order=order,
            )
            departments.append(d)

        # Assign faculty/department to staff and student profiles
        for u in users['students'] + users['instructors'] + users['support']:
            fac = random.choice(faculties)
            fac_depts = [d for d in departments if d.faculty == fac]
            p = u.profile
            p.faculty = fac
            p.department = random.choice(fac_depts) if fac_depts else departments[0]
            p.save()

        # ── 11. PROGRAMS ─────────────────────────────────────────────────────
        self.stdout.write("📖 Creating programs...")
        prog_raw = [
            (departments[0], 'BSc Software Engineering', 'BSC-SE', 'undergraduate',
             Decimal('3.0'), 360, Decimal('50.00'), Decimal('9250.00'), 80, True, 0),
            (departments[0], 'MSc Advanced Software Engineering', 'MSC-ASE', 'masters',
             Decimal('1.0'), 180, Decimal('75.00'), Decimal('14500.00'), 40, False, 1),
            (departments[1], 'BSc Artificial Intelligence', 'BSC-AI', 'undergraduate',
             Decimal('3.0'), 360, Decimal('50.00'), Decimal('9250.00'), 60, True, 0),
            (departments[1], 'PhD Artificial Intelligence', 'PHD-AI', 'phd',
             Decimal('4.0'), 480, Decimal('100.00'), Decimal('18000.00'), 15, False, 1),
            (departments[2], 'BSc Cybersecurity', 'BSC-CYS', 'undergraduate',
             Decimal('3.0'), 360, Decimal('50.00'), Decimal('9250.00'), 50, False, 0),
            (departments[3], 'BEng Civil Engineering', 'BENG-CVE', 'undergraduate',
             Decimal('4.0'), 480, Decimal('50.00'), Decimal('9250.00'), 70, True, 0),
            (departments[4], 'BEng Electrical Engineering', 'BENG-EEE', 'undergraduate',
             Decimal('4.0'), 480, Decimal('50.00'), Decimal('9250.00'), 60, False, 0),
            (departments[6], 'BSc Finance & Accounting', 'BSC-FNA', 'undergraduate',
             Decimal('3.0'), 360, Decimal('50.00'), Decimal('9250.00'), 75, True, 0),
            (departments[6], 'MBA Finance', 'MBA-FIN', 'masters',
             Decimal('1.0'), 180, Decimal('100.00'), Decimal('17500.00'), 35, True, 1),
            (departments[9], 'BSc Nursing', 'BSC-NRS', 'undergraduate',
             Decimal('3.0'), 360, Decimal('50.00'), Decimal('9250.00'), 80, True, 0),
            (departments[11], 'BA English & Creative Writing', 'BA-ECW', 'undergraduate',
             Decimal('3.0'), 360, Decimal('50.00'), Decimal('9250.00'), 60, False, 0),
            (departments[12], 'BA Digital Media & Design', 'BA-DMD', 'undergraduate',
             Decimal('3.0'), 360, Decimal('50.00'), Decimal('9250.00'), 50, False, 0),
        ]
        programs = []
        for (dept, name, code, degree, dur, cred, app_fee, tuit, max_stu, feat, order) in prog_raw:
            base_name = name.split()[-1]
            # Real-world semester credit limits by level:
            # Undergraduate: 15–21 units/semester | Postgraduate/PhD: 12–18
            _sem_cap = 18 if degree in ('undergraduate',) else (
                15 if degree in ('masters', 'postgraduate') else 12
            )
            p = Program.objects.create(
                department=dept, name=name, code=code,
                degree_level=degree, duration_years=dur,
                credits_required=cred, application_fee=app_fee,
                tuition_fee=tuit, max_students=max_stu,
                max_credits_per_semester=_sem_cap,
                is_featured=feat, is_active=True, display_order=order,
                tagline=f"Shape your future with {name}",
                overview=fake.text(max_nb_chars=200),
                description=fake.text(max_nb_chars=400),
                available_study_modes=['full_time', 'online', 'blended'],
                entry_requirements=[
                    "Minimum 5 GCSEs at grade C/4 or above including English and Maths",
                    "A-Levels: AAB or equivalent BTEC",
                    "English proficiency: IELTS 6.0 or equivalent",
                    f"Strong passion for {base_name}",
                ],
                core_courses=[
                    f"{code}-101 Foundations of {base_name}",
                    f"{code}-201 Intermediate {base_name}",
                    f"{code}-301 Advanced {base_name}",
                    f"{code}-401 {base_name} Research Methods",
                ],
                specialization_tracks=[
                    f"{base_name} & Innovation",
                    f"Applied {base_name}",
                    f"Digital {base_name}",
                ],
                learning_outcomes=[
                    f"Demonstrate comprehensive knowledge of {base_name}",
                    "Apply theoretical knowledge to real-world problems",
                    "Communicate complex ideas effectively in professional contexts",
                    "Lead and collaborate in multidisciplinary teams",
                ],
                career_paths=[
                    f"Senior {base_name} Specialist",
                    f"{base_name} Consultant",
                    f"Research Analyst – {base_name}",
                    f"Project Manager ({base_name})",
                ],
                avg_starting_salary="$45,000 - $70,000",
                job_placement_rate=random.randint(80, 97),
                meta_description=f"Study {name} at MIU — accredited, flexible, globally recognised.",
                meta_keywords=f"{name}, {code}, MIU, university degree, {dept.faculty.name}",
            )
            programs.append(p)

        # Assign program to student profiles
        for u in users['students']:
            p = u.profile
            if p.department:
                dept_progs = [pr for pr in programs if pr.department == p.department]
                if dept_progs:
                    p.program = random.choice(dept_progs)
                    p.save()

        # ── 12. ACADEMIC SESSIONS ────────────────────────────────────────────
        self.stdout.write("📅 Creating academic sessions...")
        sessions = []
        # ── Term-name resolver ────────────────────────────────────────────────
        # Reads the `term_dates` JSON on an AcademicSession and returns the
        # ordered list of term names regardless of naming convention.
        #   first/second  →  ['first', 'second']
        #   autumn/spring →  ['autumn', 'spring']
        #   fall/spring/summer → ['fall', 'spring', 'summer']
        def get_term_names(session_obj):
            """Return sorted term name strings from a session's term_dates JSON."""
            return [t['term'] for t in (session_obj.term_dates or [])]

        session_data = [
            {
                'name': '2023/2024',
                'term_dates': [
                    {'term': 'first',  'start': '2023-09-04', 'end': '2024-01-19'},
                    {'term': 'second', 'start': '2024-01-29', 'end': '2024-05-31'},
                ],
                'registration_start': date(2023, 8, 28),
                'registration_end':   date(2023, 9, 1),
                'status': 'closed', 'is_current': False,
            },
            {
                'name': '2024/2025',
                'term_dates': [
                    {'term': 'first',  'start': '2024-09-02', 'end': '2025-01-17'},
                    {'term': 'second', 'start': '2025-01-27', 'end': '2025-05-30'},
                ],
                'registration_start': date(2024, 8, 26),
                'registration_end':   date(2024, 8, 30),
                'status': 'active', 'is_current': True,
            },
            {
                'name': '2025/2026',
                'term_dates': [
                    {'term': 'first',  'start': '2025-09-01', 'end': '2026-01-16'},
                    {'term': 'second', 'start': '2026-01-26', 'end': '2026-05-29'},
                ],
                'registration_start': date(2025, 8, 25),
                'registration_end':   date(2026, 4, 30),  # open now for seeding
                'status': 'upcoming', 'is_current': False,
            },
            # ── NEW: 2026/2027 — second year of a student's 2-session program ──
            {
                'name': '2026/2027',
                'term_dates': [
                    {'term': 'first',  'start': '2026-09-07', 'end': '2027-01-15'},
                    {'term': 'second', 'start': '2027-01-25', 'end': '2027-05-28'},
                ],
                'registration_start': date(2026, 8, 24),
                'registration_end':   date(2027, 4, 30),
                'status': 'upcoming', 'is_current': False,
            },
        ]
        for sd in session_data:
            s = AcademicSession.objects.create(
                name=sd['name'],
                term_dates=sd['term_dates'],
                registration_start=sd['registration_start'],
                registration_end=sd['registration_end'],
                status=sd['status'],
                is_current=sd['is_current'],
            )
            sessions.append(s)
        current_session = sessions[1]   # 2024/2025  (used by general seeding)
        session_y1      = sessions[2]   # 2025/2026  (student's Year 1 & 2)
        session_y2      = sessions[3]   # 2026/2027  (student's Year 3 & beyond)
        open_session    = session_y1    # keep alias used by rest of seed

        # ── 13. ACADEMIC COURSES (units within programs) ──────────────────────
        self.stdout.write("📚 Creating academic courses...")
        # Format: (program, course_type, code, name, year, semester, credits, icon, color_primary, color_secondary)
        # Each program has enough courses per level/semester to exceed max unit requirements.
        # Students can pick from core, elective, and general options — plenty of variety per slot.
        ac_raw = [
            # ══════════════════════════════════════════════════════════════════════
            # BSc Software Engineering — programs[0]  (3 years)
            # ══════════════════════════════════════════════════════════════════════
            # Year 1 — Semester 1
            (programs[0], 'general',  'SE100',  'Academic Skills & Research Methods',         1, 'first',  2, 'book',           'gray',   'slate'),
            (programs[0], 'core',     'SE101',  'Introduction to Programming',                1, 'first',  3, 'terminal',       'blue',   'indigo'),
            (programs[0], 'core',     'SE102',  'Mathematics for Computing I',                1, 'first',  3, 'calculator',     'indigo', 'blue'),
            (programs[0], 'elective', 'SE106',  'Introduction to Web Technologies',           1, 'first',  3, 'globe',          'cyan',   'sky'),
            (programs[0], 'elective', 'SE107',  'Logic & Discrete Mathematics',               1, 'first',  3, 'sigma',          'violet', 'indigo'),
            (programs[0], 'general',  'SE108',  'Study Skills & Critical Thinking',           1, 'first',  2, 'lightbulb',      'amber',  'yellow'),
            # Year 1 — Semester 2
            (programs[0], 'core',     'SE103',  'Data Structures & Algorithms',               1, 'second', 3, 'layers',         'blue',   'cyan'),
            (programs[0], 'core',     'SE104',  'Object-Oriented Programming',                1, 'second', 3, 'code-2',         'sky',    'blue'),
            (programs[0], 'general',  'SE105',  'Communication Skills',                       1, 'second', 2, 'message-square', 'gray',   'zinc'),
            (programs[0], 'elective', 'SE109',  'Linux & Command Line Fundamentals',          1, 'second', 3, 'terminal',       'gray',   'slate'),
            (programs[0], 'elective', 'SE110',  'Version Control & Collaboration (Git)',      1, 'second', 2, 'git-branch',     'orange', 'amber'),
            (programs[0], 'general',  'SE111',  'Professional Ethics in Computing',           1, 'second', 2, 'scale',          'teal',   'cyan'),
            # Year 2 — Semester 1
            (programs[0], 'core',     'SE201',  'Software Design & Architecture',             2, 'first',  4, 'layout',         'blue',   'cyan'),
            (programs[0], 'core',     'SE202',  'Database Systems',                           2, 'first',  3, 'database',       'teal',   'cyan'),
            (programs[0], 'core',     'SE203',  'Operating Systems',                          2, 'first',  3, 'server',         'gray',   'blue'),
            (programs[0], 'elective', 'SE207',  'Human-Computer Interaction',                 2, 'first',  3, 'mouse-pointer',  'pink',   'rose'),
            (programs[0], 'elective', 'SE208',  'Agile & Scrum Methodologies',                2, 'first',  3, 'repeat',         'green',  'emerald'),
            (programs[0], 'elective', 'SE209',  'Scripting & Automation (Python)',            2, 'first',  3, 'code',           'yellow', 'amber'),
            # Year 2 — Semester 2
            (programs[0], 'core',     'SE204',  'Computer Networks',                          2, 'second', 3, 'network',        'sky',    'indigo'),
            (programs[0], 'core',     'SE205',  'Software Testing & Quality Assurance',       2, 'second', 3, 'check-circle',   'green',  'teal'),
            (programs[0], 'elective', 'SE206',  'Mobile Application Development',             2, 'second', 3, 'smartphone',     'cyan',   'sky'),
            (programs[0], 'elective', 'SE210',  'API Design & RESTful Services',              2, 'second', 3, 'plug',           'indigo', 'blue'),
            (programs[0], 'elective', 'SE211',  'Game Development Fundamentals',              2, 'second', 3, 'gamepad-2',      'purple', 'violet'),
            (programs[0], 'general',  'SE212',  'Project Management Essentials',              2, 'second', 2, 'clipboard-list', 'teal',   'green'),
            # Year 3 — Semester 1
            (programs[0], 'elective', 'SE301',  'Cloud Computing & DevOps',                   3, 'first',  3, 'cloud',          'sky',    'blue'),
            (programs[0], 'core',     'SE302',  'Artificial Intelligence Foundations',        3, 'first',  3, 'brain-circuit',  'violet', 'purple'),
            (programs[0], 'core',     'SE303',  'Cybersecurity Fundamentals',                 3, 'first',  3, 'shield',         'red',    'orange'),
            (programs[0], 'elective', 'SE306',  'Microservices & Container Orchestration',    3, 'first',  3, 'boxes',          'teal',   'cyan'),
            (programs[0], 'elective', 'SE307',  'Machine Learning for Developers',            3, 'first',  3, 'cpu',            'purple', 'fuchsia'),
            (programs[0], 'elective', 'SE308',  'Blockchain & Distributed Ledger Tech',       3, 'first',  3, 'link',           'amber',  'yellow'),
            # Year 3 — Semester 2
            (programs[0], 'core',     'SE304',  'Capstone Software Project',                  3, 'second', 6, 'rocket',         'indigo', 'violet'),
            (programs[0], 'elective', 'SE305',  'Entrepreneurship & Tech Startups',           3, 'second', 3, 'lightbulb',      'yellow', 'amber'),
            (programs[0], 'elective', 'SE309',  'Advanced Web Development (Full Stack)',       3, 'second', 3, 'layout-grid',    'blue',   'sky'),
            (programs[0], 'elective', 'SE310',  'IoT & Embedded Systems',                     3, 'second', 3, 'wifi',           'green',  'teal'),
            (programs[0], 'general',  'SE311',  'Professional Practice & Career Skills',      3, 'second', 2, 'briefcase',      'gray',   'zinc'),

            # ══════════════════════════════════════════════════════════════════════
            # MSc Advanced Software Engineering — programs[1]  (1 year)
            # ══════════════════════════════════════════════════════════════════════
            (programs[1], 'core',     'ASE501', 'Advanced Algorithms & Complexity',           1, 'first',  4, 'cpu',            'indigo', 'blue'),
            (programs[1], 'core',     'ASE502', 'Distributed Systems & Microservices',        1, 'first',  4, 'share-2',        'sky',    'cyan'),
            (programs[1], 'elective', 'ASE505', 'Cloud-Native Architecture',                  1, 'first',  4, 'cloud',          'blue',   'sky'),
            (programs[1], 'elective', 'ASE506', 'Security Engineering',                       1, 'first',  4, 'shield',         'red',    'orange'),
            (programs[1], 'elective', 'ASE507', 'Advanced Database Engineering',              1, 'first',  4, 'database',       'teal',   'cyan'),
            (programs[1], 'core',     'ASE503', 'Machine Learning Engineering',               1, 'second', 4, 'brain',          'purple', 'violet'),
            (programs[1], 'core',     'ASE504', 'MSc Research Thesis',                        1, 'second', 8, 'file-text',      'gray',   'blue'),
            (programs[1], 'elective', 'ASE508', 'DevOps & Platform Engineering',              1, 'second', 4, 'server',         'gray',   'slate'),
            (programs[1], 'elective', 'ASE509', 'Software Leadership & Team Dynamics',        1, 'second', 4, 'users',          'green',  'emerald'),
            (programs[1], 'elective', 'ASE510', 'Emerging Technologies Seminar',              1, 'second', 3, 'zap',            'amber',  'yellow'),

            # ══════════════════════════════════════════════════════════════════════
            # BSc Artificial Intelligence — programs[2]  (3 years)
            # ══════════════════════════════════════════════════════════════════════
            # Year 1 — Semester 1
            (programs[2], 'core',     'AI101',  'Foundations of Artificial Intelligence',     1, 'first',  3, 'brain-circuit',  'violet', 'purple'),
            (programs[2], 'core',     'AI102',  'Python for AI',                              1, 'first',  3, 'code',           'blue',   'indigo'),
            (programs[2], 'general',  'AI105',  'Academic & Research Skills',                 1, 'first',  2, 'book',           'gray',   'slate'),
            (programs[2], 'elective', 'AI106',  'Introduction to Data Science',               1, 'first',  3, 'bar-chart',      'teal',   'cyan'),
            (programs[2], 'elective', 'AI107',  'Logic & Reasoning for AI',                   1, 'first',  3, 'sigma',          'indigo', 'violet'),
            # Year 1 — Semester 2
            (programs[2], 'core',     'AI103',  'Linear Algebra & Calculus for ML',           1, 'second', 3, 'sigma',          'indigo', 'violet'),
            (programs[2], 'core',     'AI104',  'Probability & Statistics',                   1, 'second', 3, 'bar-chart',      'purple', 'fuchsia'),
            (programs[2], 'elective', 'AI108',  'Databases for AI Applications',              1, 'second', 3, 'database',       'teal',   'cyan'),
            (programs[2], 'elective', 'AI109',  'Ethics in Technology',                       1, 'second', 2, 'scale',          'gray',   'slate'),
            (programs[2], 'general',  'AI110',  'Communication & Presentation Skills',        1, 'second', 2, 'message-square', 'gray',   'zinc'),
            # Year 2 — Semester 1
            (programs[2], 'core',     'AI201',  'Machine Learning Fundamentals',              2, 'first',  4, 'cpu',            'purple', 'fuchsia'),
            (programs[2], 'core',     'AI202',  'Data Engineering & Big Data',                2, 'first',  3, 'database',       'teal',   'cyan'),
            (programs[2], 'elective', 'AI205',  'Time Series Analysis',                       2, 'first',  3, 'trending-up',    'blue',   'indigo'),
            (programs[2], 'elective', 'AI206',  'Recommender Systems',                        2, 'first',  3, 'star',           'amber',  'yellow'),
            (programs[2], 'elective', 'AI207',  'Cloud Platforms for AI',                     2, 'first',  3, 'cloud',          'sky',    'blue'),
            # Year 2 — Semester 2
            (programs[2], 'core',     'AI203',  'Natural Language Processing',                2, 'second', 3, 'message-circle', 'fuchsia','pink'),
            (programs[2], 'core',     'AI204',  'Computer Vision',                            2, 'second', 3, 'eye',            'violet', 'purple'),
            (programs[2], 'elective', 'AI208',  'Explainable AI & Model Interpretability',    2, 'second', 3, 'search',         'orange', 'amber'),
            (programs[2], 'elective', 'AI209',  'Robotics & Autonomous Systems',              2, 'second', 3, 'cpu',            'blue',   'sky'),
            (programs[2], 'elective', 'AI210',  'Advanced Statistical Modelling',             2, 'second', 3, 'activity',       'purple', 'violet'),
            # Year 3 — Semester 1
            (programs[2], 'elective', 'AI301',  'Deep Learning & Neural Networks',            3, 'first',  3, 'network',        'violet', 'indigo'),
            (programs[2], 'elective', 'AI302',  'Reinforcement Learning',                     3, 'first',  3, 'target',         'purple', 'violet'),
            (programs[2], 'elective', 'AI305',  'Generative AI & Large Language Models',      3, 'first',  3, 'sparkles',       'fuchsia','pink'),
            (programs[2], 'elective', 'AI306',  'AI for Healthcare',                          3, 'first',  3, 'heart-pulse',    'red',    'rose'),
            (programs[2], 'elective', 'AI307',  'Edge AI & Embedded Intelligence',            3, 'first',  3, 'wifi',           'green',  'teal'),
            # Year 3 — Semester 2
            (programs[2], 'core',     'AI303',  'AI Ethics & Responsible AI',                 3, 'second', 3, 'scale',          'gray',   'slate'),
            (programs[2], 'core',     'AI304',  'AI Capstone Project',                        3, 'second', 6, 'rocket',         'fuchsia','violet'),
            (programs[2], 'elective', 'AI308',  'AI Product Development',                     3, 'second', 3, 'package',        'blue',   'indigo'),
            (programs[2], 'elective', 'AI309',  'Federated Learning & Privacy-Preserving AI', 3, 'second', 3, 'lock',           'teal',   'cyan'),

            # ══════════════════════════════════════════════════════════════════════
            # PhD Artificial Intelligence — programs[3]  (4 years)
            # ══════════════════════════════════════════════════════════════════════
            (programs[3], 'core',     'PHD701', 'Doctoral Research Methodology',              1, 'first',  6, 'file-text',      'gray',   'slate'),
            (programs[3], 'core',     'PHD702', 'Advanced Machine Learning Theory',           1, 'first',  6, 'brain',          'purple', 'violet'),
            (programs[3], 'elective', 'PHD703', 'Research Seminar Series I',                  1, 'second', 4, 'mic',            'blue',   'indigo'),
            (programs[3], 'elective', 'PHD704', 'Advanced Deep Learning',                     1, 'second', 6, 'network',        'violet', 'indigo'),
            (programs[3], 'core',     'PHD705', 'PhD Thesis (Year 1 Progress)',               1, 'second', 8, 'scroll',         'gray',   'blue'),
            (programs[3], 'core',     'PHD801', 'PhD Thesis (Year 2 Research)',               2, 'first',  12,'scroll',         'gray',   'blue'),
            (programs[3], 'elective', 'PHD802', 'Research Seminar Series II',                 2, 'second', 4, 'mic',            'blue',   'sky'),
            (programs[3], 'core',     'PHD901', 'PhD Thesis (Year 3 Writing)',                3, 'first',  12,'scroll',         'gray',   'blue'),
            (programs[3], 'elective', 'PHD902', 'Academic Publication & Dissemination',       3, 'second', 4, 'book-open',      'green',  'teal'),
            (programs[3], 'core',     'PHD001', 'PhD Thesis Submission & Viva',               4, 'second', 12,'award',          'gold',   'amber'),

            # ══════════════════════════════════════════════════════════════════════
            # BSc Cybersecurity — programs[4]  (3 years)
            # ══════════════════════════════════════════════════════════════════════
            # Year 1 — Semester 1
            (programs[4], 'core',     'CYS101', 'Introduction to Cybersecurity',              1, 'first',  3, 'shield',         'red',    'orange'),
            (programs[4], 'core',     'CYS102', 'Networking Fundamentals',                    1, 'first',  3, 'network',        'blue',   'sky'),
            (programs[4], 'general',  'CYS105', 'Academic Skills & Professional Ethics',      1, 'first',  2, 'book',           'gray',   'slate'),
            (programs[4], 'elective', 'CYS106', 'Introduction to Programming for Security',   1, 'first',  3, 'code',           'indigo', 'blue'),
            (programs[4], 'elective', 'CYS107', 'Computer Architecture & Organisation',       1, 'first',  3, 'cpu',            'amber',  'yellow'),
            # Year 1 — Semester 2
            (programs[4], 'core',     'CYS103', 'Operating Systems Security',                 1, 'second', 3, 'lock',           'red',    'rose'),
            (programs[4], 'core',     'CYS104', 'Cryptography & PKI',                         1, 'second', 3, 'key',            'amber',  'yellow'),
            (programs[4], 'elective', 'CYS108', 'Linux Security Administration',              1, 'second', 3, 'terminal',       'gray',   'slate'),
            (programs[4], 'elective', 'CYS109', 'Security Scripting with Python',             1, 'second', 3, 'code-2',         'blue',   'indigo'),
            (programs[4], 'general',  'CYS110', 'Communication Skills for IT',                1, 'second', 2, 'message-square', 'gray',   'zinc'),
            # Year 2 — Semester 1
            (programs[4], 'core',     'CYS201', 'Ethical Hacking & Pen Testing',              2, 'first',  4, 'bug',            'red',    'pink'),
            (programs[4], 'elective', 'CYS203', 'Cloud Security Fundamentals',                2, 'first',  3, 'cloud',          'sky',    'blue'),
            (programs[4], 'elective', 'CYS204', 'Web Application Security',                   2, 'first',  3, 'globe',          'orange', 'red'),
            (programs[4], 'elective', 'CYS205', 'Vulnerability Assessment & Management',      2, 'first',  3, 'search',         'red',    'orange'),
            (programs[4], 'elective', 'CYS206', 'Identity & Access Management',               2, 'first',  3, 'user-check',     'teal',   'cyan'),
            # Year 2 — Semester 2
            (programs[4], 'core',     'CYS202', 'Digital Forensics',                          2, 'second', 3, 'search',         'orange', 'amber'),
            (programs[4], 'elective', 'CYS207', 'Incident Response & Threat Intelligence',    2, 'second', 3, 'alert-triangle', 'red',    'rose'),
            (programs[4], 'elective', 'CYS208', 'Network Intrusion Detection',                2, 'second', 3, 'wifi-off',       'rose',   'red'),
            (programs[4], 'elective', 'CYS209', 'Secure Software Development',                2, 'second', 3, 'code-2',         'indigo', 'violet'),
            (programs[4], 'general',  'CYS210', 'Project Management for Security Teams',      2, 'second', 2, 'clipboard-list', 'teal',   'green'),
            # Year 3 — Semester 1
            (programs[4], 'elective', 'CYS301', 'Malware Analysis & Reverse Engineering',     3, 'first',  3, 'code-2',         'rose',   'red'),
            (programs[4], 'elective', 'CYS303', 'Red Team Operations',                        3, 'first',  3, 'target',         'red',    'pink'),
            (programs[4], 'elective', 'CYS304', 'IoT Security',                               3, 'first',  3, 'wifi',           'amber',  'orange'),
            (programs[4], 'elective', 'CYS305', 'Governance, Risk & Compliance (GRC)',        3, 'first',  3, 'scale',          'blue',   'indigo'),
            (programs[4], 'elective', 'CYS306', 'Mobile & Endpoint Security',                 3, 'first',  3, 'smartphone',     'violet', 'purple'),
            # Year 3 — Semester 2
            (programs[4], 'core',     'CYS302', 'Security Operations & SIEM',                 3, 'second', 3, 'monitor',        'red',    'orange'),
            (programs[4], 'elective', 'CYS307', 'Cyber Law & Policy',                         3, 'second', 3, 'file-text',      'gray',   'blue'),
            (programs[4], 'elective', 'CYS308', 'Capstone: Security Assessment Project',      3, 'second', 6, 'rocket',         'red',    'rose'),

            # ══════════════════════════════════════════════════════════════════════
            # BEng Civil Engineering — programs[5]  (4 years)
            # ══════════════════════════════════════════════════════════════════════
            # Year 1 — Semester 1
            (programs[5], 'core',     'CVE101', 'Structural Analysis I',                      1, 'first',  3, 'building',       'orange', 'amber'),
            (programs[5], 'core',     'CVE102', 'Engineering Mathematics I',                  1, 'first',  3, 'calculator',     'amber',  'yellow'),
            (programs[5], 'general',  'CVE105', 'Engineering Drawing & Visualisation',        1, 'first',  2, 'pen-tool',       'gray',   'slate'),
            (programs[5], 'elective', 'CVE106', 'Introduction to Environmental Science',      1, 'first',  3, 'leaf',           'green',  'emerald'),
            (programs[5], 'elective', 'CVE107', 'Engineering Surveying',                      1, 'first',  3, 'map',            'teal',   'cyan'),
            # Year 1 — Semester 2
            (programs[5], 'core',     'CVE103', 'Engineering Drawing & CAD',                  1, 'second', 3, 'pen-tool',       'orange', 'red'),
            (programs[5], 'core',     'CVE104', 'Materials Science',                          1, 'second', 3, 'layers',         'amber',  'orange'),
            (programs[5], 'elective', 'CVE108', 'Engineering Mathematics II',                 1, 'second', 3, 'calculator',     'indigo', 'blue'),
            (programs[5], 'elective', 'CVE109', 'Soil Mechanics Introduction',                1, 'second', 3, 'mountain',       'brown',  'amber'),
            (programs[5], 'general',  'CVE110', 'Communication & Report Writing',             1, 'second', 2, 'message-square', 'gray',   'zinc'),
            # Year 2 — Semester 1
            (programs[5], 'core',     'CVE201', 'Structural Analysis II',                     2, 'first',  4, 'building-2',     'orange', 'amber'),
            (programs[5], 'core',     'CVE202', 'Fluid Mechanics',                            2, 'first',  3, 'droplets',       'blue',   'cyan'),
            (programs[5], 'elective', 'CVE205', 'Highway & Pavement Engineering',             2, 'first',  3, 'map',            'gray',   'slate'),
            (programs[5], 'elective', 'CVE206', 'Construction Technology',                    2, 'first',  3, 'hard-hat',       'amber',  'orange'),
            (programs[5], 'elective', 'CVE207', 'Engineering Hydrology',                      2, 'first',  3, 'droplets',       'sky',    'blue'),
            # Year 2 — Semester 2
            (programs[5], 'core',     'CVE203', 'Geotechnical Engineering',                   2, 'second', 3, 'mountain',       'orange', 'yellow'),
            (programs[5], 'core',     'CVE204', 'Transportation Engineering',                 2, 'second', 3, 'map',            'amber',  'orange'),
            (programs[5], 'elective', 'CVE208', 'Bridge Engineering',                         2, 'second', 3, 'building',       'orange', 'red'),
            (programs[5], 'elective', 'CVE209', 'Water Supply & Sanitation Engineering',      2, 'second', 3, 'droplets',       'blue',   'teal'),
            (programs[5], 'general',  'CVE210', 'Engineering Management & Economics',         2, 'second', 2, 'trending-up',    'green',  'emerald'),
            # Year 3 — Semester 1
            (programs[5], 'elective', 'CVE301', 'Environmental Engineering',                  3, 'first',  3, 'leaf',           'green',  'emerald'),
            (programs[5], 'elective', 'CVE303', 'Foundation Engineering',                     3, 'first',  3, 'layers',         'amber',  'yellow'),
            (programs[5], 'elective', 'CVE304', 'Earthquake Engineering',                     3, 'first',  3, 'activity',       'red',    'orange'),
            (programs[5], 'elective', 'CVE305', 'Offshore & Marine Structures',               3, 'first',  3, 'anchor',         'blue',   'sky'),
            (programs[5], 'elective', 'CVE306', 'Urban Planning & Infrastructure',            3, 'first',  3, 'map-pin',        'teal',   'cyan'),
            # Year 3 — Semester 2
            (programs[5], 'core',     'CVE302', 'Concrete & Steel Design',                    3, 'second', 3, 'hard-hat',       'orange', 'amber'),
            (programs[5], 'elective', 'CVE307', 'Finite Element Methods',                     3, 'second', 3, 'grid',           'indigo', 'blue'),
            (programs[5], 'elective', 'CVE308', 'Waste Management Engineering',               3, 'second', 3, 'trash-2',        'green',  'teal'),
            # Year 4 — Semester 1
            (programs[5], 'core',     'CVE401', 'Project Management in Civil Eng.',           4, 'first',  3, 'clipboard-list', 'teal',   'cyan'),
            (programs[5], 'elective', 'CVE403', 'BIM & Digital Construction',                 4, 'first',  3, 'layout-grid',    'blue',   'indigo'),
            (programs[5], 'elective', 'CVE404', 'Smart Infrastructure & IoT',                 4, 'first',  3, 'wifi',           'sky',    'blue'),
            (programs[5], 'elective', 'CVE405', 'Risk Assessment & Safety Engineering',       4, 'first',  3, 'alert-triangle', 'red',    'orange'),
            # Year 4 — Semester 2
            (programs[5], 'core',     'CVE402', 'BEng Capstone Project',                      4, 'second', 8, 'rocket',         'red',    'orange'),
            (programs[5], 'elective', 'CVE406', 'Sustainable Construction',                   4, 'second', 3, 'leaf',           'green',  'emerald'),
            (programs[5], 'elective', 'CVE407', 'Advanced Structural Design',                 4, 'second', 3, 'building-2',     'orange', 'amber'),

            # ══════════════════════════════════════════════════════════════════════
            # BEng Electrical Engineering — programs[6]  (4 years)
            # ══════════════════════════════════════════════════════════════════════
            # Year 1 — Semester 1
            (programs[6], 'core',     'EEE101', 'Circuit Theory & Electronics',               1, 'first',  3, 'zap',            'yellow', 'amber'),
            (programs[6], 'core',     'EEE102', 'Engineering Mathematics I',                  1, 'first',  3, 'calculator',     'amber',  'yellow'),
            (programs[6], 'general',  'EEE105', 'Engineering Drawing & Design',               1, 'first',  2, 'pen-tool',       'gray',   'slate'),
            (programs[6], 'elective', 'EEE106', 'Introduction to Programming (C)',            1, 'first',  3, 'code',           'blue',   'indigo'),
            (programs[6], 'elective', 'EEE107', 'Engineering Physics',                        1, 'first',  3, 'activity',       'purple', 'violet'),
            # Year 1 — Semester 2
            (programs[6], 'core',     'EEE103', 'Digital Electronics',                        1, 'second', 3, 'cpu',            'yellow', 'lime'),
            (programs[6], 'elective', 'EEE108', 'Engineering Mathematics II',                 1, 'second', 3, 'sigma',          'indigo', 'blue'),
            (programs[6], 'elective', 'EEE109', 'Introduction to Signals & Systems',          1, 'second', 3, 'activity',       'teal',   'cyan'),
            (programs[6], 'general',  'EEE110', 'Communication & Technical Writing',          1, 'second', 2, 'message-square', 'gray',   'zinc'),
            (programs[6], 'elective', 'EEE111', 'Computer Architecture for Engineers',        1, 'second', 3, 'server',         'gray',   'blue'),
            # Year 2 — Semester 1
            (programs[6], 'core',     'EEE201', 'Electromagnetics',                           2, 'first',  3, 'magnet',         'amber',  'orange'),
            (programs[6], 'elective', 'EEE203', 'Analogue Electronics',                       2, 'first',  3, 'zap',            'yellow', 'lime'),
            (programs[6], 'elective', 'EEE204', 'Microprocessors & Embedded Systems',         2, 'first',  4, 'cpu',            'blue',   'indigo'),
            (programs[6], 'elective', 'EEE205', 'Signals & Systems',                          2, 'first',  3, 'activity',       'teal',   'cyan'),
            (programs[6], 'elective', 'EEE206', 'Electrical Machines I',                      2, 'first',  3, 'settings',       'orange', 'amber'),
            # Year 2 — Semester 2
            (programs[6], 'core',     'EEE202', 'Power Systems I',                            2, 'second', 4, 'bolt',           'yellow', 'amber'),
            (programs[6], 'elective', 'EEE207', 'Telecommunications I',                       2, 'second', 3, 'radio',          'sky',    'blue'),
            (programs[6], 'elective', 'EEE208', 'Digital Signal Processing',                  2, 'second', 3, 'bar-chart',      'purple', 'violet'),
            (programs[6], 'elective', 'EEE209', 'Instrumentation & Measurements',             2, 'second', 3, 'gauge',          'teal',   'green'),
            (programs[6], 'general',  'EEE210', 'Engineering Economics & Management',         2, 'second', 2, 'trending-up',    'green',  'emerald'),
            # Year 3 — Semester 1
            (programs[6], 'core',     'EEE301', 'Control Systems',                            3, 'first',  3, 'sliders',        'orange', 'amber'),
            (programs[6], 'elective', 'EEE303', 'Power Electronics',                          3, 'first',  3, 'zap',            'amber',  'yellow'),
            (programs[6], 'elective', 'EEE304', 'High Voltage Engineering',                   3, 'first',  3, 'bolt',           'red',    'orange'),
            (programs[6], 'elective', 'EEE305', 'VLSI Design',                                3, 'first',  3, 'layers',         'indigo', 'violet'),
            (programs[6], 'elective', 'EEE306', 'Wireless Communications',                    3, 'first',  3, 'wifi',           'sky',    'cyan'),
            # Year 3 — Semester 2
            (programs[6], 'elective', 'EEE302', 'Renewable Energy Systems',                   3, 'second', 3, 'sun',            'green',  'emerald'),
            (programs[6], 'elective', 'EEE307', 'Smart Grid Technology',                      3, 'second', 3, 'network',        'teal',   'cyan'),
            (programs[6], 'elective', 'EEE308', 'Robotics & Automation',                      3, 'second', 3, 'cpu',            'blue',   'indigo'),
            # Year 4 — Semester 1
            (programs[6], 'elective', 'EEE401', 'Advanced Power Systems',                     4, 'first',  3, 'bolt',           'yellow', 'lime'),
            (programs[6], 'elective', 'EEE402', 'Satellite & Space Communications',           4, 'first',  3, 'radio',          'violet', 'purple'),
            (programs[6], 'elective', 'EEE403', 'AI for Electrical Engineering',              4, 'first',  3, 'brain',          'purple', 'fuchsia'),
            (programs[6], 'elective', 'EEE404', 'Electric Vehicles & Charging Infrastructure',4, 'first',  3, 'car',            'green',  'teal'),
            # Year 4 — Semester 2
            (programs[6], 'core',     'EEE400', 'BEng Electrical Capstone Project',           4, 'second', 8, 'rocket',         'yellow', 'amber'),
            (programs[6], 'elective', 'EEE405', 'Energy Storage Systems',                     4, 'second', 3, 'battery-charging','green', 'emerald'),
            (programs[6], 'elective', 'EEE406', 'Advanced Control & Optimisation',            4, 'second', 3, 'sliders',        'orange', 'red'),

            # ══════════════════════════════════════════════════════════════════════
            # BSc Finance & Accounting — programs[7]  (3 years)
            # ══════════════════════════════════════════════════════════════════════
            # Year 1 — Semester 1
            (programs[7], 'core',     'FNA101', 'Financial Accounting Principles',            1, 'first',  3, 'book-open',      'green',  'emerald'),
            (programs[7], 'core',     'FNA102', 'Business Economics',                         1, 'first',  3, 'trending-up',    'emerald','teal'),
            (programs[7], 'general',  'FNA105', 'Academic & Study Skills',                    1, 'first',  2, 'book',           'gray',   'slate'),
            (programs[7], 'elective', 'FNA106', 'Business Law & Regulation',                  1, 'first',  3, 'scale',          'blue',   'indigo'),
            (programs[7], 'elective', 'FNA107', 'Microsoft Excel for Finance',                1, 'first',  2, 'table',          'green',  'lime'),
            # Year 1 — Semester 2
            (programs[7], 'core',     'FNA103', 'Introduction to Finance',                    1, 'second', 3, 'dollar-sign',    'green',  'lime'),
            (programs[7], 'core',     'FNA104', 'Quantitative Methods',                       1, 'second', 3, 'calculator',     'teal',   'cyan'),
            (programs[7], 'elective', 'FNA108', 'Principles of Marketing',                    1, 'second', 3, 'megaphone',      'orange', 'amber'),
            (programs[7], 'elective', 'FNA109', 'Introduction to Macroeconomics',             1, 'second', 3, 'trending-up',    'blue',   'sky'),
            (programs[7], 'general',  'FNA110', 'Communication & Business Writing',           1, 'second', 2, 'message-square', 'gray',   'zinc'),
            # Year 2 — Semester 1
            (programs[7], 'core',     'FNA201', 'Corporate Finance',                          2, 'first',  4, 'trending-up',    'emerald','teal'),
            (programs[7], 'core',     'FNA202', 'Management Accounting',                      2, 'first',  3, 'pie-chart',      'green',  'emerald'),
            (programs[7], 'elective', 'FNA205', 'Financial Econometrics',                     2, 'first',  3, 'activity',       'indigo', 'blue'),
            (programs[7], 'elective', 'FNA206', 'International Finance',                      2, 'first',  3, 'globe',          'sky',    'blue'),
            (programs[7], 'elective', 'FNA207', 'Banking & Financial Institutions',           2, 'first',  3, 'landmark',       'teal',   'green'),
            # Year 2 — Semester 2
            (programs[7], 'core',     'FNA203', 'Taxation',                                   2, 'second', 3, 'receipt',        'teal',   'green'),
            (programs[7], 'elective', 'FNA208', 'Financial Risk Management',                  2, 'second', 3, 'alert-triangle', 'red',    'orange'),
            (programs[7], 'elective', 'FNA209', 'Mergers, Acquisitions & Valuations',         2, 'second', 3, 'git-merge',      'purple', 'violet'),
            (programs[7], 'elective', 'FNA210', 'Public Sector Finance',                      2, 'second', 3, 'landmark',       'blue',   'indigo'),
            (programs[7], 'general',  'FNA211', 'Entrepreneurship & New Ventures',            2, 'second', 2, 'lightbulb',      'amber',  'yellow'),
            # Year 3 — Semester 1
            (programs[7], 'core',     'FNA302', 'Auditing & Assurance',                       3, 'first',  3, 'check-square',   'emerald','teal'),
            (programs[7], 'elective', 'FNA304', 'Derivatives & Financial Engineering',        3, 'first',  3, 'trending-up',    'violet', 'purple'),
            (programs[7], 'elective', 'FNA305', 'Corporate Governance & Ethics',              3, 'first',  3, 'scale',          'gray',   'slate'),
            (programs[7], 'elective', 'FNA306', 'FinTech & Digital Finance',                  3, 'first',  3, 'smartphone',     'blue',   'indigo'),
            (programs[7], 'elective', 'FNA307', 'Portfolio Management',                       3, 'first',  3, 'bar-chart-2',    'green',  'teal'),
            # Year 3 — Semester 2
            (programs[7], 'elective', 'FNA301', 'Investment Analysis',                        3, 'second', 3, 'bar-chart-2',    'green',  'lime'),
            (programs[7], 'core',     'FNA303', 'Financial Reporting & IFRS',                 3, 'second', 3, 'file-bar-chart', 'teal',   'green'),
            (programs[7], 'elective', 'FNA308', 'Advanced Taxation',                          3, 'second', 3, 'receipt',        'amber',  'orange'),
            (programs[7], 'elective', 'FNA309', 'Capstone: Finance Research Project',         3, 'second', 6, 'rocket',         'green',  'emerald'),

            # ══════════════════════════════════════════════════════════════════════
            # MBA Finance — programs[8]  (1 year — postgraduate)
            # ══════════════════════════════════════════════════════════════════════
            (programs[8], 'core',     'MBA501', 'Managerial Economics',                       1, 'first',  4, 'briefcase',      'teal',   'cyan'),
            (programs[8], 'core',     'MBA502', 'Organisational Behaviour',                   1, 'first',  4, 'users',          'cyan',   'sky'),
            (programs[8], 'elective', 'MBA507', 'Leadership & Strategic Management',          1, 'first',  4, 'award',          'blue',   'indigo'),
            (programs[8], 'elective', 'MBA508', 'Operations Management',                      1, 'first',  4, 'settings',       'gray',   'slate'),
            (programs[8], 'elective', 'MBA509', 'Marketing Management',                       1, 'first',  3, 'megaphone',      'orange', 'amber'),
            (programs[8], 'core',     'MBA503', 'Strategic Financial Management',             1, 'second', 4, 'pie-chart',      'emerald','teal'),
            (programs[8], 'core',     'MBA504', 'Business Research Methods',                  1, 'second', 4, 'search',         'teal',   'emerald'),
            (programs[8], 'elective', 'MBA505', 'International Business & Trade',             1, 'second', 3, 'globe',          'blue',   'cyan'),
            (programs[8], 'core',     'MBA506', 'MBA Dissertation',                           1, 'second', 8, 'file-text',      'gray',   'teal'),
            (programs[8], 'elective', 'MBA510', 'Corporate Social Responsibility',            1, 'second', 3, 'heart',          'green',  'emerald'),
            (programs[8], 'elective', 'MBA511', 'Digital Transformation in Business',         1, 'second', 3, 'zap',            'violet', 'purple'),

            # ══════════════════════════════════════════════════════════════════════
            # BSc Nursing — programs[9]  (3 years)
            # ══════════════════════════════════════════════════════════════════════
            # Year 1 — Semester 1
            (programs[9], 'core',     'NRS101', 'Anatomy & Physiology I',                     1, 'first',  4, 'heart-pulse',    'red',    'rose'),
            (programs[9], 'core',     'NRS102', 'Foundations of Nursing Practice',            1, 'first',  3, 'stethoscope',    'rose',   'pink'),
            (programs[9], 'general',  'NRS105', 'Academic & Study Skills for Nurses',         1, 'first',  2, 'book',           'gray',   'slate'),
            (programs[9], 'elective', 'NRS106', 'Introduction to Psychology',                 1, 'first',  3, 'brain',          'purple', 'violet'),
            (programs[9], 'elective', 'NRS107', 'Healthcare Ethics & Law',                    1, 'first',  3, 'scale',          'blue',   'indigo'),
            # Year 1 — Semester 2
            (programs[9], 'core',     'NRS103', 'Anatomy & Physiology II',                    1, 'second', 4, 'activity',       'red',    'pink'),
            (programs[9], 'core',     'NRS104', 'Pharmacology I',                             1, 'second', 3, 'pill',           'pink',   'rose'),
            (programs[9], 'elective', 'NRS108', 'Nutrition & Dietetics',                      1, 'second', 3, 'apple',          'green',  'teal'),
            (programs[9], 'elective', 'NRS109', 'Medical Terminology',                        1, 'second', 2, 'book-open',      'gray',   'zinc'),
            (programs[9], 'general',  'NRS110', 'Communication Skills in Healthcare',         1, 'second', 2, 'message-square', 'gray',   'slate'),
            # Year 2 — Semester 1
            (programs[9], 'core',     'NRS201', 'Clinical Nursing Practice I',                2, 'first',  5, 'stethoscope',    'rose',   'pink'),
            (programs[9], 'core',     'NRS202', 'Microbiology & Infection Control',           2, 'first',  3, 'shield-check',   'red',    'rose'),
            (programs[9], 'elective', 'NRS205', 'Palliative & End-of-Life Care',              2, 'first',  3, 'heart',          'purple', 'violet'),
            (programs[9], 'elective', 'NRS206', 'Surgical Nursing',                           2, 'first',  3, 'activity',       'blue',   'sky'),
            (programs[9], 'elective', 'NRS207', 'Pharmacology II',                            2, 'first',  3, 'pill',           'pink',   'fuchsia'),
            # Year 2 — Semester 2
            (programs[9], 'core',     'NRS203', 'Mental Health Nursing',                      2, 'second', 3, 'brain',          'purple', 'violet'),
            (programs[9], 'core',     'NRS204', 'Child & Family Nursing',                     2, 'second', 3, 'baby',           'pink',   'rose'),
            (programs[9], 'elective', 'NRS208', 'Gerontological Nursing',                     2, 'second', 3, 'user',           'amber',  'yellow'),
            (programs[9], 'elective', 'NRS209', 'Critical Care Nursing',                      2, 'second', 3, 'heart-pulse',    'red',    'orange'),
            (programs[9], 'general',  'NRS210', 'Leadership & Management in Nursing',         2, 'second', 2, 'users',          'teal',   'cyan'),
            # Year 3 — Semester 1
            (programs[9], 'elective', 'NRS301', 'Community & Public Health Nursing',          3, 'first',  3, 'map-pin',        'green',  'teal'),
            (programs[9], 'elective', 'NRS304', 'Midwifery Fundamentals',                     3, 'first',  3, 'baby',           'pink',   'rose'),
            (programs[9], 'elective', 'NRS305', 'Oncology Nursing',                           3, 'first',  3, 'shield',         'purple', 'violet'),
            (programs[9], 'elective', 'NRS306', 'Neuroscience & Neurological Nursing',        3, 'first',  3, 'brain',          'indigo', 'violet'),
            (programs[9], 'elective', 'NRS307', 'Telemedicine & Digital Health',              3, 'first',  3, 'smartphone',     'blue',   'sky'),
            # Year 3 — Semester 2
            (programs[9], 'core',     'NRS302', 'Clinical Nursing Practice II',               3, 'second', 5, 'heart',          'red',    'rose'),
            (programs[9], 'core',     'NRS303', 'Evidence-Based Practice & Research',         3, 'second', 4, 'file-text',      'gray',   'red'),
            (programs[9], 'elective', 'NRS308', 'Nursing Dissertation',                       3, 'second', 6, 'scroll',         'gray',   'rose'),
            (programs[9], 'elective', 'NRS309', 'Advanced Clinical Assessment',               3, 'second', 3, 'stethoscope',    'rose',   'red'),

            # ══════════════════════════════════════════════════════════════════════
            # BA English & Creative Writing — programs[10]  (3 years)
            # ══════════════════════════════════════════════════════════════════════
            # Year 1 — Semester 1
            (programs[10], 'core',     'ECW101', 'Introduction to Literary Theory',           1, 'first',  3, 'book',           'purple', 'violet'),
            (programs[10], 'core',     'ECW102', 'Academic Writing Skills',                   1, 'first',  2, 'pen',            'violet', 'purple'),
            (programs[10], 'general',  'ECW105', 'Research & Study Skills',                   1, 'first',  2, 'book-open',      'gray',   'slate'),
            (programs[10], 'elective', 'ECW106', 'World Literature Survey',                   1, 'first',  3, 'globe',          'indigo', 'blue'),
            (programs[10], 'elective', 'ECW107', 'Introduction to Linguistics',               1, 'first',  3, 'message-circle', 'fuchsia','pink'),
            # Year 1 — Semester 2
            (programs[10], 'core',     'ECW103', 'Poetry: Form & Tradition',                  1, 'second', 3, 'feather',        'fuchsia','pink'),
            (programs[10], 'elective', 'ECW108', 'Short Fiction Workshop',                    1, 'second', 3, 'pen-line',       'violet', 'purple'),
            (programs[10], 'elective', 'ECW109', 'American Literature',                       1, 'second', 3, 'book',           'blue',   'sky'),
            (programs[10], 'general',  'ECW110', 'Communication & Presentation Skills',       1, 'second', 2, 'message-square', 'gray',   'zinc'),
            (programs[10], 'elective', 'ecw111', 'introduction to drama studies',             1, 'second', 3, 'film',           'pink',   'rose'),
            (programs[10], 'elective', 'ecw112', 'digital reading & media literacy',          1, 'second', 3, 'monitor',        'sky',    'blue'),
            # Year 2 — Semester 1
            (programs[10], 'core',     'ECW202', 'British Literature 1800–Present',           2, 'first',  3, 'library',        'purple', 'indigo'),
            (programs[10], 'elective', 'ECW203', 'Postcolonial Literature',                   2, 'first',  3, 'globe',          'amber',  'yellow'),
            (programs[10], 'elective', 'ECW204', 'Journalism & Non-Fiction Writing',          2, 'first',  3, 'newspaper',      'gray',   'slate'),
            (programs[10], 'elective', 'ECW205', 'Drama & Performance Text',                  2, 'first',  3, 'film',           'rose',   'pink'),
            # Year 2 — Semester 2
            (programs[10], 'elective', 'ECW201', 'Fiction Writing Workshop',                  2, 'second', 3, 'pen-line',       'violet', 'purple'),
            (programs[10], 'elective', 'ECW206', 'Digital Storytelling & Content Creation',   2, 'second', 3, 'video',          'blue',   'indigo'),
            (programs[10], 'elective', 'ECW207', 'Publishing & the Literary Industry',        2, 'second', 3, 'book-marked',    'teal',   'cyan'),
            (programs[10], 'general',  'ECW208', 'Editing & Proofreading',                    2, 'second', 2, 'check-square',   'green',  'emerald'),
            (programs[10], 'elective', 'ecw209', 'satire & irony in literature',              2, 'second', 3, 'pen',            'amber',  'yellow'),
            (programs[10], 'elective', 'ecw210', 'translation studies',                       2, 'second', 3, 'globe',          'teal',   'emerald'),
            # Year 3 — Semester 1
            (programs[10], 'elective', 'ECW301', 'Screenwriting & Drama',                     3, 'first',  3, 'film',           'pink',   'rose'),
            (programs[10], 'elective', 'ECW303', 'Gothic & Horror Fiction',                   3, 'first',  3, 'moon',           'gray',   'slate'),
            (programs[10], 'elective', 'ECW304', 'Travel Writing & Memoir',                   3, 'first',  3, 'map',            'amber',  'orange'),
            (programs[10], 'elective', 'ECW305', 'Contemporary Poetry Writing',               3, 'first',  3, 'feather',        'purple', 'fuchsia'),
            # Year 3 — Semester 2
            (programs[10], 'core',     'ECW302', 'Dissertation in English',                   3, 'second', 6, 'scroll',         'gray',   'purple'),
            (programs[10], 'elective', 'ECW306', 'Children\'s Literature & Writing',          3, 'second', 3, 'book-open',      'pink',   'rose'),
            (programs[10], 'elective', 'ECW307', 'Advanced Novel Writing',                    3, 'second', 3, 'pen',            'violet', 'indigo'),

            # ══════════════════════════════════════════════════════════════════════
            # BA Digital Media & Design — programs[11]  (3 years)
            # ══════════════════════════════════════════════════════════════════════
            # Year 1 — Semester 1
            (programs[11], 'core',     'DMD101', 'Principles of Graphic Design',              1, 'first',  3, 'image',          'pink',   'rose'),
            (programs[11], 'core',     'DMD102', 'Typography & Layout',                       1, 'first',  2, 'type',           'rose',   'pink'),
            (programs[11], 'general',  'DMD105', 'Art History & Visual Culture',              1, 'first',  2, 'book',           'gray',   'slate'),
            (programs[11], 'elective', 'DMD106', 'Introduction to Digital Tools (Adobe)',     1, 'first',  3, 'layers',         'orange', 'red'),
            (programs[11], 'elective', 'DMD107', 'Photography for Beginners',                 1, 'first',  3, 'camera',         'amber',  'yellow'),
            # Year 1 — Semester 2
            (programs[11], 'core',     'DMD103', 'Colour Theory & Visual Communication',      1, 'second', 3, 'palette',        'fuchsia','purple'),
            (programs[11], 'elective', 'DMD108', 'Web Design Fundamentals (HTML/CSS)',        1, 'second', 3, 'globe',          'blue',   'sky'),
            (programs[11], 'elective', 'DMD109', 'Brand Identity Basics',                     1, 'second', 3, 'star',           'pink',   'fuchsia'),
            (programs[11], 'general',  'DMD110', 'Communication & Presentation Skills',       1, 'second', 2, 'message-square', 'gray',   'zinc'),
            (programs[11], 'elective', 'DMD111', 'Print Design & Editorial Layout',           1, 'second', 3, 'layout',         'orange', 'amber'),
            (programs[11], 'elective', 'DMD112', 'Infographics & Data Visualisation',         1, 'second', 3, 'bar-chart',      'teal',   'cyan'),
            # Year 2 — Semester 1
            (programs[11], 'core',     'DMD201', 'UX & Interaction Design',                   2, 'first',  3, 'mouse-pointer',  'pink',   'fuchsia'),
            (programs[11], 'elective', 'DMD203', 'UI Design & Prototyping (Figma)',           2, 'first',  3, 'layout',         'violet', 'purple'),
            (programs[11], 'elective', 'DMD204', 'Social Media Content & Strategy',           2, 'first',  3, 'instagram',      'rose',   'pink'),
            (programs[11], 'elective', 'DMD205', '3D Modelling & Visualisation',              2, 'first',  3, 'box',            'blue',   'indigo'),
            # Year 2 — Semester 2
            (programs[11], 'core',     'DMD202', 'Digital Photography & Video',               2, 'second', 3, 'camera',         'rose',   'pink'),
            (programs[11], 'elective', 'DMD206', 'Video Editing & Post-Production',           2, 'second', 3, 'film',           'gray',   'slate'),
            (programs[11], 'elective', 'DMD207', 'Illustration & Digital Art',                2, 'second', 3, 'image',          'fuchsia','violet'),
            (programs[11], 'general',  'DMD208', 'Project Management for Creatives',          2, 'second', 2, 'clipboard-list', 'teal',   'cyan'),
            # Year 3 — Semester 1
            (programs[11], 'elective', 'DMD301', 'Motion Graphics & Animation',               3, 'first',  3, 'play-circle',    'fuchsia','violet'),
            (programs[11], 'elective', 'DMD303', 'Augmented & Virtual Reality Design',        3, 'first',  3, 'glasses',        'purple', 'indigo'),
            (programs[11], 'elective', 'DMD304', 'Game Art & Asset Design',                   3, 'first',  3, 'gamepad-2',      'blue',   'violet'),
            (programs[11], 'elective', 'DMD305', 'Advertising & Campaign Design',             3, 'first',  3, 'megaphone',      'orange', 'amber'),
            # Year 3 — Semester 2
            (programs[11], 'core',     'DMD302', 'Design Capstone Portfolio',                 3, 'second', 6, 'layout-grid',    'pink',   'rose'),
            (programs[11], 'elective', 'DMD306', 'Advanced Typography & Publication Design',  3, 'second', 3, 'type',           'violet', 'purple'),
            (programs[11], 'elective', 'DMD307', 'Freelancing & Creative Business',           3, 'second', 3, 'briefcase',      'teal',   'green'),
        ]
        academic_courses = []
        for (prog, ctype, code, name, year, semester, credits, icon, col1, col2) in ac_raw:
            c = Course.objects.create(
                program=prog,
                name=name, code=code,
                course_type=ctype,
                credit_units=credits,
                year_of_study=year,
                semester=semester,
                description=fake.text(max_nb_chars=300),
                learning_outcomes=[
                    f"Understand core principles of {name}",
                    "Apply concepts to practical scenarios",
                    "Critically evaluate relevant literature and methods",
                    "Demonstrate competence through assessed coursework",
                ],
                icon=icon,
                color_primary=col1,
                color_secondary=col2,
                is_active=True,
                display_order=len(academic_courses),
            )
            academic_courses.append(c)

        # ── 14. COURSE INTAKES ───────────────────────────────────────────────
        self.stdout.write("📅 Creating course intakes...")
        intakes = []
        period_months = {'january': 1, 'may': 5, 'september': 9}
        for program in programs:
            for period, month in period_months.items():
                for year in [2025, 2026]:
                    deadline = date(year, month, 1) - timedelta(days=45)
                    intakes.append(CourseIntake.objects.create(
                        program=program,
                        intake_period=period,
                        year=year,
                        start_date=date(year, month, 15),
                        application_deadline=deadline,
                        available_slots=random.randint(30, 100),
                        is_active=True,
                    ))

        # ── 15. ALL REQUIRED PAYMENTS ────────────────────────────────────────
        self.stdout.write("💷 Creating required payments...")
        payment_purposes = [
            ('School Fees',               'student',   Decimal('9250.00')),
            ('Library Fees',              'student',   Decimal('120.00')),
            ('Laboratory Fees',           'student',   Decimal('350.00')),
            ('Student Union Fee',         'student',   Decimal('80.00')),
            ('Examination Fee',           'student',   Decimal('200.00')),
            ('Staff Development Levy',    'staff',     Decimal('150.00')),
            ('Application Processing Fee','applicant', Decimal('50.00')),
        ]
        for program in programs:
            prog_courses = [c for c in academic_courses if c.program == program]
            for purpose, who, amount in payment_purposes:
                AllRequiredPayments.objects.create(
                    program=program,
                    course=random.choice(prog_courses) if prog_courses and random.random() > 0.5 else None,
                    academic_session=current_session,
                    semester=random.choice(['first', 'second', 'annual']),
                    purpose=purpose,
                    who_to_pay=who,
                    amount=amount,
                    due_date=date(2025, 9, 30),
                    is_active=True,
                )

        # ── 15b. FEE PAYMENTS ────────────────────────────────────────────────
        self.stdout.write("💳 Creating fee payments...")
        all_required = list(AllRequiredPayments.objects.filter(is_active=True, who_to_pay='student'))
        if all_required and verified_students:
            for student in verified_students:
                for fee in random.sample(all_required, k=min(3, len(all_required))):
                    pstatus = random.choice(['success', 'success', 'pending', 'failed', 'processing'])
                    FeePayment.objects.create(
                        fee=fee,
                        user=student,
                        amount=fee.amount,
                        currency='GBP',
                        status=pstatus,
                        payment_method=random.choice(['card', 'paypal', 'bank_transfer']),
                        gateway_payment_id=f"pi_{uuid.uuid4().hex[:24]}",
                        card_last4=str(random.randint(1000, 9999)),
                        card_brand=random.choice(['Visa', 'Mastercard', 'Amex']),
                        paid_at=timezone.now() - timedelta(days=random.randint(1, 60))
                        if pstatus == 'success' else None,
                        payment_metadata={
                            'stripe_charge_id': f"ch_{uuid.uuid4().hex[:24]}",
                            'ip_address': fake.ipv4(),
                            'device': random.choice(['desktop', 'mobile', 'tablet']),
                        },
                        failure_reason='Insufficient funds' if pstatus == 'failed' else '',
                    )
        self.stdout.write(self.style.SUCCESS(f"   ✅ {FeePayment.objects.count()} fee payments created"))

        # ── 16. COURSE APPLICATIONS ──────────────────────────────────────────
        self.stdout.write("📝 Creating course applications...")
        applications = []
        for student in verified_students:
            program = random.choice(programs)
            prog_intakes = [i for i in intakes if i.program == program]
            if not prog_intakes:
                continue
            intake = random.choice(prog_intakes)
            status = random.choice([
                'draft', 'pending_payment', 'payment_complete',
                'under_review', 'approved', 'rejected',
            ])
            is_approved = status == 'approved'
            admitted = is_approved and random.random() > 0.4
            dept_approved = admitted and random.random() > 0.5
            adm_number = (
                f"ADM-{timezone.now().year}-{uuid.uuid4().hex[:8].upper()}"
                if admitted else None
            )
            study_mode_options = program.available_study_modes or ['full_time']
            app = CourseApplication.objects.create(
                user=student,
                program=program,
                intake=intake,
                study_mode=random.choice(study_mode_options),
                first_name=student.first_name, last_name=student.last_name,
                email=student.email,
                phone=fake.phone_number()[:20],
                date_of_birth=fake.date_of_birth(minimum_age=18, maximum_age=35),
                gender=random.choice(['male', 'female', 'other']),
                nationality=fake.country(),
                address_line1=fake.street_address(),
                address_line2=fake.secondary_address() if random.random() > 0.5 else '',
                city=fake.city(), state=fake.state(), postal_code=fake.postcode(),
                country=fake.country(),
                highest_qualification=random.choice(
                    ['High School', 'Associate Degree', 'Bachelor Degree']
                ),
                institution_name=fake.company(),
                graduation_year=str(random.randint(2015, 2024)),
                gpa_or_grade=f"{random.uniform(2.5, 4.0):.2f}",
                language_skill=random.choice(['ielts', 'toefl', 'pte', 'cambridge', 'none']),
                language_score=Decimal(str(round(random.uniform(5.5, 9.0), 1)))
                if random.random() > 0.3 else None,
                work_experience_years=random.randint(0, 10),
                personal_statement=fake.text(max_nb_chars=800),
                how_did_you_hear=random.choice(
                    ['Social Media', 'Friend', 'Website', 'Advertisement', 'Open Day']
                ),
                how_did_you_hear_other='',
                scholarship=random.choice([True, False]),
                accept_privacy_policy=True,
                accept_terms_conditions=True,
                marketing_consent=random.choice([True, False]),
                emergency_contact_name=fake.name(),
                emergency_contact_phone=fake.phone_number()[:20],
                emergency_contact_relationship=random.choice(
                    ['Parent', 'Sibling', 'Spouse', 'Guardian']
                ),
                emergency_contact_email=fake.email(),
                emergency_contact_address=fake.address()[:255],
                status=status,
                reviewer=random.choice(verified_admins) if random.random() > 0.5 else None,
                review_notes=fake.text(max_nb_chars=200) if random.random() > 0.5 else '',
                submitted_at=timezone.now() - timedelta(days=random.randint(1, 90))
                if status != 'draft' else None,
                payment_status=random.choice(['pending', 'completed', 'failed']),
                in_processing=status in ['under_review', 'payment_complete'],
                admission_accepted=admitted,
                admission_accepted_at=timezone.now() - timedelta(days=random.randint(1, 30))
                if admitted else None,
                admission_number=adm_number,
                department_approved=dept_approved,
                department_approved_at=timezone.now() - timedelta(days=random.randint(1, 15))
                if dept_approved else None,
                department_approved_by=random.choice(verified_admins) if dept_approved else None,
            )
            applications.append(app)

        # ── 17. APPLICATION DOCUMENTS ────────────────────────────────────────
        # Note: FileField requires actual files on disk in production.
        # In seeding we leave the file field blank (it is optional/blank=True behaviour
        # for ApplicationDocument.file is NOT blank=True in the model, so we set
        # original_filename and file_size but leave file blank — the field has
        # no blank=True but migrations allow null on existing rows via default '').
        self.stdout.write("📎 Creating application documents (metadata only)...")
        for app in applications:
            for doc_type in random.sample(
                ['transcript', 'certificate', 'cv', 'passport', 'id_document', 'recommendation'],
                k=random.randint(2, 5)
            ):
                ApplicationDocument.objects.create(
                    application=app, file_type=doc_type,
                    file='documents/placeholder.pdf',   # placeholder path (no physical file needed for seeding)
                    original_filename=f"{doc_type}_{uuid.uuid4().hex[:6]}.pdf",
                    file_size=random.randint(100_000, 5_000_000),
                )

        # ── 17b. COURSE REGISTRATIONS & GRADES ─────────────────────────────────
        self.stdout.write("📋 Creating course registrations and grades...")
        grade_letters = ['A', 'A', 'A', 'B', 'B', 'B', 'C', 'C', 'D', 'F']
        grade_scores  = [95,  90,  87,  83,  80,  77,  73,  70,  62,  45]

        # Use the open registration session (2025/2026 has registration_end in the future)
        open_session = sessions[2]  # 2025/2026 — registration_end = 2026-04-30

        for student in verified_students:
            # pick courses from the student's own program; fall back to all courses
            student_program = student.profile.program
            if student_program:
                own_courses = [c for c in academic_courses if c.program == student_program]
            else:
                own_courses = academic_courses
            pool = own_courses if own_courses else academic_courses
            sample_courses = random.sample(pool, k=min(random.randint(5, 8), len(pool)))
            for ac in sample_courses:
                try:
                    reg = CourseRegistration(
                        student=student,
                        course=ac,
                        session=open_session,
                        term=ac.semester,
                        status=random.choice(['approved', 'approved', 'dropped', 'pending']),
                    )
                    reg.save(skip_window_check=True)
                except Exception:
                    continue  # skip duplicates / prerequisite violations
                # Create a grade for approved registrations
                if reg.status == 'approved':
                    grade_idx = random.randint(0, len(grade_letters) - 1)
                    CourseGrade.objects.get_or_create(
                        student=student,
                        course=ac,
                        session=open_session,
                        term=ac.semester,
                        defaults=dict(
                            grade=grade_letters[grade_idx],
                            score=Decimal(str(grade_scores[grade_idx] + random.randint(-4, 4))),
                            credit_units=ac.credit_units,
                            is_passed=grade_idx < 8,
                            recorded_by=random.choice(verified_instructors),
                        )
                    )
        self.stdout.write(self.style.SUCCESS(
            f"   ✅ {CourseRegistration.objects.count()} registrations, "
            f"{CourseGrade.objects.count()} grades created"
        ))

        # ── FULL PROGRAM GPA SEEDING for 'student' and 'student2' ──────────────
        # Each student gets registrations + grades for ALL courses in their program,
        # split across 2 sessions (4 semesters total):
        #   session_y1 (2025/2026) → program years where year_of_study is in first half
        #   session_y2 (2026/2027) → remaining program years
        #
        # Term detection is generic — reads the session's term_dates JSON keys
        # so it works for first/second AND autumn/winter/spring/summer conventions.
        #
        # Credit load per semester is capped at program.max_credits_per_semester
        # (undergrad=18, masters=15, phd=12) — we register up to that cap and
        # mark the rest 'dropped' so the DB stays clean.
        #
        # Nigerian 5-point grading: A=5, B=4, C=3, D=2, F=0
        self.stdout.write("🎓 Seeding full program GPA for 'student' and 'student2'...")

        full_gpa_grade_pool = [
            ('A', Decimal('88.00'), True,  5),
            ('A', Decimal('92.00'), True,  5),
            ('A', Decimal('85.00'), True,  5),
            ('B', Decimal('78.00'), True,  4),
            ('B', Decimal('74.00'), True,  4),
            ('B', Decimal('71.00'), True,  4),
            ('C', Decimal('67.00'), True,  3),
            ('C', Decimal('63.00'), True,  3),
            ('D', Decimal('55.00'), True,  2),
            ('F', Decimal('38.00'), False, 0),
        ]

        # ── helpers ───────────────────────────────────────────────────────────
        def session_terms(sess):
            """Return ordered list of term-name strings from a session's JSON."""
            return [t['term'] for t in (sess.term_dates or [])]

        def semester_to_term(semester_value, term_names):
            """
            Map a Course.semester value ('first'/'second' or 'autumn'/'spring' etc.)
            to a term string that exists in the session.
            Strategy:
              1. Exact match — use as-is if it appears in term_names.
              2. Positional fallback — 'first'/'1'/'autumn'/'fall' → term_names[0];
                 'second'/'2'/'spring'/'winter' → term_names[1], etc.
            """
            if semester_value in term_names:
                return semester_value
            # Positional mapping buckets (index 0 = first half, index 1 = second half)
            _buckets = [
                {'first', '1', 'autumn', 'fall', 'semester1', 'sem1'},
                {'second', '2', 'spring', 'winter', 'semester2', 'sem2'},
                {'third', '3', 'summer', 'semester3', 'sem3'},
            ]
            for idx, bucket in enumerate(_buckets):
                if semester_value.lower() in bucket and idx < len(term_names):
                    return term_names[idx]
            return term_names[0]  # safe default

        gpa_target_usernames = ['student', 'student2']

        for username in gpa_target_usernames:
            try:
                target_user = User.objects.get(username=username)
            except User.DoesNotExist:
                continue

            target_profile = target_user.profile
            target_program = target_profile.program
            if not target_program:
                self.stdout.write(self.style.WARNING(
                    f"   ⚠ {username} has no program assigned — skipping full GPA seed"
                ))
                continue

            max_cap = target_program.max_credits_per_semester or 18
            all_prog_courses = [c for c in academic_courses if c.program == target_program]
            if not all_prog_courses:
                continue

            # ── Split program years across 2 sessions ─────────────────────────
            # For a 3-year UG: years 1–2 → session_y1, year 3 → session_y2
            # For a 4-year UG: years 1–2 → session_y1, years 3–4 → session_y2
            # For a 1-year PG: semester 'first' → session_y1, 'second' → session_y2
            all_years = sorted(set(c.year_of_study for c in all_prog_courses))
            split_idx = max(1, len(all_years) // 2)
            years_s1  = set(all_years[:split_idx])      # → session_y1
            years_s2  = set(all_years[split_idx:]) or {all_years[-1]}  # → session_y2

            # For 1-year programs the two years are the same; split on semester instead
            if len(all_years) == 1:
                years_s1 = {all_years[0]}
                years_s2 = {all_years[0]}

            terms_y1 = session_terms(session_y1)   # ['first', 'second']
            terms_y2 = session_terms(session_y2)   # ['first', 'second']

            self.stdout.write(
                f"   → {username} | program: {target_program.code} | "
                f"courses: {len(all_prog_courses)} | cap/sem: {max_cap}"
            )

            total_weighted = Decimal('0.00')
            total_units    = 0
            sem_unit_tracker = {}   # (session_id, term) → units registered so far

            # Sort courses: year asc, semester, then by pk for determinism
            sem_order = {'first': 0, 'second': 1, 'autumn': 0, 'spring': 1,
                         'fall': 0, 'winter': 1, 'summer': 2}
            sorted_courses = sorted(
                all_prog_courses,
                key=lambda c: (c.year_of_study, sem_order.get(c.semester, 99), c.pk)
            )

            for ac in sorted_courses:
                # Choose which session this course belongs to
                if len(all_years) == 1:
                    # 1-year program: first-half semesters → session_y1, rest → session_y2
                    _first_half_terms = {'first', 'autumn', 'fall', '1'}
                    use_session = session_y1 if ac.semester.lower() in _first_half_terms else session_y2
                    use_terms   = terms_y1   if use_session is session_y1 else terms_y2
                else:
                    use_session = session_y1 if ac.year_of_study in years_s1 else session_y2
                    use_terms   = terms_y1   if use_session is session_y1 else terms_y2

                term_name  = semester_to_term(ac.semester, use_terms)
                slot_key   = (use_session.id, term_name)

                # Enforce per-semester credit cap
                already_registered = sem_unit_tracker.get(slot_key, 0)
                if already_registered + ac.credit_units > max_cap:
                    # Register as dropped so the record exists but doesn't count
                    try:
                        CourseRegistration.objects.get_or_create(
                            student=target_user,
                            course=ac,
                            session=use_session,
                            term=term_name,
                            defaults={'status': 'dropped'},
                        )
                    except Exception:
                        pass
                    continue  # don't grade over-cap courses

                sem_unit_tracker[slot_key] = already_registered + ac.credit_units

                g_letter, g_score, g_passed, g_points = random.choice(full_gpa_grade_pool)

                # Register (approved)
                try:
                    reg, _ = CourseRegistration.objects.get_or_create(
                        student=target_user,
                        course=ac,
                        session=use_session,
                        term=term_name,
                        defaults={'status': 'approved'},
                    )
                    if reg.status != 'approved':
                        reg.status = 'approved'
                        reg.save(skip_clean=True, skip_window_check=True)
                except Exception:
                    continue

                # Grade
                try:
                    grade_obj, created = CourseGrade.objects.get_or_create(
                        student=target_user,
                        course=ac,
                        session=use_session,
                        term=term_name,
                        defaults=dict(
                            grade=g_letter,
                            score=g_score,
                            credit_units=ac.credit_units,
                            is_passed=g_passed,
                            result_status='released',
                            recorded_by=random.choice(verified_instructors),
                        )
                    )
                    if not created:
                        grade_obj.grade         = g_letter
                        grade_obj.score         = g_score
                        grade_obj.credit_units  = ac.credit_units
                        grade_obj.is_passed     = g_passed
                        grade_obj.result_status = 'released'
                        grade_obj.save()
                except Exception:
                    continue

                total_weighted += Decimal(str(g_points)) * ac.credit_units
                total_units    += ac.credit_units

            cgpa = (total_weighted / total_units).quantize(Decimal('0.01')) if total_units else Decimal('0.00')

            # Per-semester breakdown for clarity
            for (sid, tname), units in sorted(sem_unit_tracker.items()):
                sess_name = session_y1.name if sid == session_y1.id else session_y2.name
                self.stdout.write(
                    f"      {sess_name} / {tname}: {units} units registered"
                )
            self.stdout.write(self.style.SUCCESS(
                f"   ✅ {username}: {total_units} total units | CGPA: {cgpa}/5.00 "
                f"| Sessions: {session_y1.name} + {session_y2.name}"
            ))

        # ── 18. APPLICATION PAYMENTS ─────────────────────────────────────────
        self.stdout.write("💰 Creating application payments...")
        for app in [a for a in applications
                    if a.status in ['payment_complete', 'under_review', 'approved']]:
            ApplicationPayment.objects.create(
                application=app,
                amount=app.program.application_fee,
                currency='USD',
                status='success',
                payment_method=random.choice(['card', 'paypal', 'bank_transfer']),
                payment_reference=f"REF-{uuid.uuid4().hex[:16].upper()}",
                gateway_payment_id=f"pi_{uuid.uuid4().hex[:24]}",
                card_last4=str(random.randint(1000, 9999)),
                card_brand=random.choice(['Visa', 'Mastercard', 'Amex']),
                paid_at=timezone.now() - timedelta(days=random.randint(1, 60)),
                payment_metadata={
                    'stripe_charge_id': f"ch_{uuid.uuid4().hex[:24]}",
                    'ip_address': fake.ipv4(),
                    'device': random.choice(['desktop', 'mobile', 'tablet']),
                },
                failure_reason='',
            )

        # (duplicate course registration block removed — registrations handled in section 17b above)

        # ── 18c. COURSE GRADES ────────────────────────────────────────────────
        self.stdout.write("📊 Creating course grades...")
        grade_map = [
            ('A', Decimal('85.00'), True),
            ('A', Decimal('90.00'), True),
            ('B', Decimal('75.00'), True),
            ('B', Decimal('70.00'), True),
            ('C', Decimal('65.00'), True),
            ('C', Decimal('60.00'), True),
            ('D', Decimal('55.00'), True),
            ('F', Decimal('40.00'), False),
            ('F', Decimal('30.00'), False),
        ]
        approved_regs = list(CourseRegistration.objects.filter(status='approved'))
        for reg in approved_regs:
            grade_letter, score, is_passed = random.choice(grade_map)
            try:
                # Find the LMS course linked to this academic course + session
                linked_lms = next(
                    (lc for lc in lms_courses
                        if lc.academic_course_id == reg.course_id and lc.session_id == current_session.id),
                    None
                )
                CourseGrade.objects.get_or_create(
                    student=reg.student,
                    course=reg.course,
                    session=current_session,
                    term=reg.term,
                    defaults=dict(
                        lms_course=linked_lms,
                        application=None,
                        score=score + Decimal(str(random.randint(-5, 5))),
                        grade=grade_letter,
                        credit_units=reg.course.credit_units,
                        is_passed=is_passed,
                        result_status=random.choice(['released', 'released', 'pending', 'withheld']),
                        recorded_by=random.choice(users['instructors']),
                    )
                )
            except Exception:
                pass
        self.stdout.write(self.style.SUCCESS(
            f"   ✅ {CourseGrade.objects.count()} course grades created"
        ))

        # ── 18d. LIBRARY ITEMS ────────────────────────────────────────────────
        self.stdout.write("📚 Creating library items...")
        admin_user = users['admins'][0]
        library_raw = [
            # (title, author, publisher, year, category, subcategory, isbn, description, tags, access, featured)
            # ── Books: Computer Science ───────────────────────────────────────
            ('Introduction to Algorithms', 'Cormen, Leiserson, Rivest, Stein',
             'MIT Press', 2022, 'Books', 'Computer Science Books',
             '9780262046305',
             'The definitive reference for algorithms and data structures. Required text for CS students.',
             'algorithms,data structures,computer science', 'members', True),
            ('Clean Code: A Handbook of Agile Software Craftsmanship', 'Robert C. Martin',
             'Prentice Hall', 2008, 'Books', 'Computer Science Books',
             '9780132350884',
             'Best practices for writing maintainable, readable code in any language.',
             'clean code,software engineering,agile', 'members', False),
            ('Deep Learning', 'Goodfellow, Bengio, Courville',
             'MIT Press', 2016, 'Books', 'Computer Science Books',
             '9780262035613',
             'Comprehensive coverage of deep learning theory and modern neural network architectures.',
             'deep learning,neural networks,machine learning', 'members', True),
            ('The Pragmatic Programmer', 'Hunt & Thomas',
             'Addison-Wesley', 2019, 'Books', 'Computer Science Books',
             '9780135957059',
             'Timeless software development wisdom for programmers at every level.',
             'programming,software development,best practices', 'members', False),
            ('Python Crash Course', 'Eric Matthes',
             'No Starch Press', 2023, 'Books', 'Computer Science Books',
             '9781718502703',
             'Hands-on project-based introduction to Python programming.',
             'python,programming,beginner', 'public', False),
            ('Design Patterns: Elements of Reusable Object-Oriented Software', 'Gang of Four',
             'Addison-Wesley', 1994, 'Books', 'Computer Science Books',
             '9780201633610',
             'The classic reference for software design patterns used throughout the industry.',
             'design patterns,object oriented,software architecture', 'members', False),
            ('Computer Networks', 'Andrew Tanenbaum',
             'Pearson', 2021, 'Books', 'Computer Science Books',
             '9780137523214',
             'Comprehensive coverage of computer networking protocols, architectures, and applications.',
             'networking,TCP/IP,protocols', 'members', False),
            ('Operating System Concepts', 'Silberschatz, Galvin, Gagne',
             'Wiley', 2018, 'Books', 'Computer Science Books',
             '9781119456339',
             'The standard OS textbook covering processes, memory, storage, and security.',
             'operating systems,processes,memory management', 'members', False),

            # ── Books: Engineering ─────────────────────────────────────────────
            ('Structural Analysis', 'Russell C. Hibbeler',
             'Pearson', 2020, 'Books', 'Engineering Books',
             '9780134610672',
             'Comprehensive coverage of structural mechanics for civil and structural engineering.',
             'structural analysis,civil engineering,statics', 'members', True),
            ('Fundamentals of Electric Circuits', 'Alexander & Sadiku',
             'McGraw-Hill', 2020, 'Books', 'Engineering Books',
             '9780078028229',
             'Essential textbook for electrical circuit analysis with worked examples.',
             'electric circuits,electrical engineering,AC DC', 'members', False),
            ('Engineering Mechanics: Statics', 'R.C. Hibbeler',
             'Pearson', 2019, 'Books', 'Engineering Books',
             '9780133918922',
             'Core mechanics text covering forces, equilibrium, and structural analysis.',
             'statics,mechanics,engineering', 'members', False),
            ('Soil Mechanics and Foundations', 'Muni Budhu',
             'Wiley', 2019, 'Books', 'Engineering Books',
             '9781119600343',
             'Comprehensive geotechnical engineering reference for civil engineering students.',
             'soil mechanics,geotechnical,foundations', 'members', False),
            ('Thermodynamics: An Engineering Approach', 'Cengel & Boles',
             'McGraw-Hill', 2019, 'Books', 'Engineering Books',
             '9780073398174',
             'Core thermodynamics textbook used in mechanical and chemical engineering programmes.',
             'thermodynamics,heat transfer,mechanical engineering', 'members', False),

            # ── Books: Business & Finance ──────────────────────────────────────
            ('Principles of Corporate Finance', 'Brealey, Myers, Allen',
             'McGraw-Hill', 2022, 'Books', 'Business & Finance Books',
             '9781260565553',
             'Authoritative corporate finance text used in MBA programmes worldwide.',
             'corporate finance,investment,valuation', 'members', True),
            ('Financial Accounting', 'Weygandt, Kimmel, Kieso',
             'Wiley', 2022, 'Books', 'Business & Finance Books',
             '9781119494683',
             'Core financial accounting text covering IFRS and US GAAP standards.',
             'financial accounting,IFRS,GAAP', 'members', False),
            ('Marketing Management', 'Philip Kotler & Kevin Lane Keller',
             'Pearson', 2016, 'Books', 'Business & Finance Books',
             '9780134236933',
             'The leading marketing management textbook with global case studies.',
             'marketing,brand management,consumer behaviour', 'members', False),
            ('The Lean Startup', 'Eric Ries',
             'Crown Business', 2011, 'Books', 'Business & Finance Books',
             '9780307887894',
             'Essential reading for entrepreneurs on building and scaling startups efficiently.',
             'startup,entrepreneurship,lean,agile', 'public', False),
            ('Competitive Strategy', 'Michael E. Porter',
             'Free Press', 1980, 'Books', 'Business & Finance Books',
             '9780684841489',
             'Foundational text on industry analysis, competitive advantage, and business strategy.',
             'strategy,competitive advantage,Porter', 'members', False),
            ('Investment Valuation', 'Aswath Damodaran',
             'Wiley', 2012, 'Books', 'Business & Finance Books',
             '9781118011522',
             'Comprehensive guide to valuing stocks, bonds, firms, and real assets.',
             'valuation,investment,DCF,financial modeling', 'members', False),

            # ── Books: Health Sciences ──────────────────────────────────────────
            ('Fundamentals of Nursing', 'Taylor, Lynn, Bartlett',
             'Lippincott Williams & Wilkins', 2023, 'Books', 'Health Sciences Books',
             '9781975168155',
             'Comprehensive nursing foundations text for pre-registration nursing students.',
             'nursing,clinical practice,patient care', 'members', True),
            ('Pharmacology for Nurses', 'Michael Patrick Adams',
             'Pearson', 2022, 'Books', 'Health Sciences Books',
             '9780136817093',
             'Core pharmacology reference with drug classifications and nursing implications.',
             'pharmacology,drugs,nursing,medication', 'members', False),
            ('Public Health: An Introduction', 'Naidoo & Wills',
             'Palgrave Macmillan', 2016, 'Books', 'Health Sciences Books',
             '9780230368941',
             'Accessible introduction to public health concepts, policy, and practice.',
             'public health,epidemiology,health policy', 'members', False),
            ("Gray's Anatomy for Students", 'Drake, Vogl, Mitchell',
             'Elsevier', 2020, 'Books', 'Health Sciences Books',
             '9780323393041',
             'Complete illustrated anatomy reference for health sciences students.',
             'anatomy,physiology,medical,nursing', 'members', True),

            # ── Books: Arts & Humanities ───────────────────────────────────────
            ('The Norton Anthology of English Literature', 'Stephen Greenblatt (ed.)',
             'Norton', 2018, 'Books', 'Arts & Humanities Books',
             '9780393603071',
             'Definitive anthology covering English literature from the Middle Ages to the present.',
             'literature,English,poetry,fiction', 'public', True),
            ('Thinking with Type', 'Ellen Lupton',
             'Princeton Architectural Press', 2010, 'Books', 'Arts & Humanities Books',
             '9781568989693',
             'Essential guide to typography for graphic designers and visual communicators.',
             'typography,design,layout,graphic design', 'public', False),
            ('The Design of Everyday Things', 'Don Norman',
             'Basic Books', 2013, 'Books', 'Arts & Humanities Books',
             '9780465050659',
             'Foundational UX and product design thinking — essential for all design students.',
             'UX,product design,usability,human factors', 'public', True),
            ('Ways of Seeing', 'John Berger',
             'Penguin', 1972, 'Books', 'Arts & Humanities Books',
             '9780140135152',
             'Influential essays on art criticism, visual culture, and the politics of looking.',
             'art criticism,visual culture,aesthetics', 'public', False),

            # ── Periodicals ───────────────────────────────────────────────────
            ('IEEE Transactions on Neural Networks and Learning Systems', 'IEEE',
             'IEEE', 2024, 'Periodicals', 'Technology Journals',
             '',
             'Peer-reviewed journal publishing research on neural networks and learning algorithms.',
             'neural networks,machine learning,IEEE', 'members', False),
            ('Journal of Structural Engineering', 'ASCE',
             'American Society of Civil Engineers', 2024, 'Periodicals', 'Engineering Journals',
             '',
             'Leading journal covering structural analysis, design, and construction technology.',
             'structural engineering,civil engineering,ASCE', 'members', False),
            ('Journal of Finance', 'American Finance Association',
             'Wiley', 2024, 'Periodicals', 'Business Journals',
             '',
             'Top-tier academic journal for financial economics research and theory.',
             'finance,financial economics,investment', 'members', False),
            ('The Lancet', 'Elsevier',
             'Elsevier', 2024, 'Periodicals', 'Health Sciences Journals',
             '',
             'Prestigious medical journal covering clinical research and global health policy.',
             'medicine,health,clinical research,Lancet', 'members', False),
            ('Nature', 'Springer Nature',
             'Springer Nature', 2024, 'Periodicals', 'Science Journals',
             '',
             'Weekly multidisciplinary scientific journal — one of the most cited in the world.',
             'science,nature,research,peer review', 'members', False),
            ('Harvard Business Review', 'Harvard Business Publishing',
             'Harvard Business Publishing', 2024, 'Periodicals', 'Business Journals',
             '',
             'Leading management and business strategy publication read by executives worldwide.',
             'business,management,strategy,HBR', 'members', False),

            # ── References ────────────────────────────────────────────────────
            ("Oxford Dictionary of English", 'Oxford University Press',
             'Oxford University Press', 2023, 'References', 'Dictionaries',
             '9780199571123',
             'Comprehensive dictionary of the English language with etymology and usage notes.',
             'dictionary,English,vocabulary,reference', 'public', False),
            ('APA Publication Manual (7th Edition)', 'American Psychological Association',
             'American Psychological Association', 2020, 'References', 'Style Guides',
             '9781433832161',
             'Official style guide for academic writing in psychology, social sciences, and health.',
             'APA,citation,academic writing,referencing', 'public', True),
            ('Chicago Manual of Style (17th Edition)', 'University of Chicago Press',
             'University of Chicago Press', 2017, 'References', 'Style Guides',
             '9780226287058',
             'The authoritative guide to manuscript preparation, editing, and citation.',
             'Chicago style,citation,editing,publishing', 'public', False),
            ('IEEE Citation Reference', 'IEEE',
             'IEEE', 2024, 'References', 'Style Guides',
             '',
             'Official IEEE referencing and citation guidelines for technical publications.',
             'IEEE,citation,referencing,technical writing', 'public', False),
            ('MIU Academic Regulations Handbook 2024/2025', 'Melchisedec International University',
             'MIU Press', 2024, 'References', 'Institutional Documents',
             '',
             'Complete academic regulations, student rights, assessment policies, and procedures.',
             'regulations,academic policy,MIU,student handbook', 'members', True),
            ('OWASP Top 10 Security Risks 2023', 'OWASP Foundation',
             'OWASP', 2023, 'References', 'Technical References',
             '',
             'Industry-standard guide to the most critical web application security vulnerabilities.',
             'cybersecurity,OWASP,security,web development', 'public', False),
        ]

        for (title, author, publisher, year, category, subcategory, isbn,
             desc, tags, access, featured) in library_raw:
            LibraryItem.objects.create(
                title=title,
                author=author,
                publisher=publisher,
                year=year,
                category=category,
                subcategory=subcategory,
                isbn=isbn,
                description=desc,
                tags=tags,
                access=access,
                featured=featured,
                language='en',
                allow_download=True,
                allow_read_online=True,
                is_active=True,
                order=0,
                created_by=admin_user,
            )
        self.stdout.write(self.style.SUCCESS(
            f"   ✅ {LibraryItem.objects.count()} library items created"
        ))

        # ── 19/20. LMS COURSES — one delivery per academic Course per session ──────
        # Every LMSCourse is tied to an academic Course. No standalone LMS courses.
        # No categories — the academic course → program → department provides all context.
        self.stdout.write("🎥 Creating LMS courses (linked to academic courses)...")
        lms_courses = []
        instructor_course_map = {}
        diff_by_year = {1: 'beginner', 2: 'intermediate', 3: 'advanced', 4: 'advanced'}

        for idx, ac in enumerate(academic_courses):
            instructor = users['instructors'][idx % len(users['instructors'])]
            diff = diff_by_year.get(ac.year_of_study, 'intermediate')
            dur = Decimal(str(round(ac.credit_units * 8.5, 1)))  # ~8.5 hrs per credit unit
            desc = (
                f"Comprehensive LMS delivery of {ac.name}. Covers all syllabus topics "
                f"through video lectures, practical exercises, and assessments aligned to "
                f"{ac.program.name} Year {ac.year_of_study}."
            )
            for sess in sessions:
                session_terms = [t['term'] for t in sess.term_dates]
                if ac.semester not in session_terms:
                    continue  # only create for sessions that include this semester
                lc = LMSCourse.objects.create(
                    title=f"{ac.name} [{sess.name}]",
                    code=f"{ac.code}-{sess.name.replace('/', '-')}",
                    academic_course=ac,
                    session=sess,
                    term=ac.semester,
                    lecturer=instructor,
                    short_description=desc[:500],
                    description='\n\n'.join([fake.text(max_nb_chars=400) for _ in range(3)]),
                    learning_objectives=[
                        f"Understand core principles of {ac.name}",
                        "Apply theoretical knowledge to practical scenarios",
                        "Demonstrate competence through assessed coursework",
                        "Critically evaluate relevant literature and methods",
                    ],
                    prerequisites=(
                        ['No prior knowledge required'] if diff == 'beginner'
                        else [f"Completion of Year {ac.year_of_study - 1} courses"]
                    ),
                    difficulty_level=diff,
                    duration_hours=dur,
                    language='English',
                    instructor=instructor,
                    instructor_name=instructor.get_full_name(),
                    instructor_bio=fake.text(max_nb_chars=300),
                    promo_video_url='https://www.youtube.com/watch?v=-mJFZp84TIY',
                    max_students=random.choice([50, 100, 200, None]),
                    enrollment_start_date=date(2025, 1, 1),
                    enrollment_end_date=date(2026, 12, 31),
                    is_published=True,
                    is_featured=random.random() > 0.7,
                    has_certificate=True,
                    certificate_template=f"template_{random.choice(['gold', 'silver', 'standard'])}",
                    meta_description=desc[:160],
                    meta_keywords=f"{ac.name}, {ac.code}, {ac.program.name}, {ac.program.department.name}",
                )
                lms_courses.append(lc)
                instructor_course_map.setdefault(instructor, []).append(lc)

        self.stdout.write(self.style.SUCCESS(
            f"   ✅ {LMSCourse.objects.count()} LMS courses created (all linked to academic courses)"
        ))

        # ── 21. LESSON SECTIONS & LESSONS ────────────────────────────────────
        self.stdout.write("📹 Creating lesson sections and lessons...")
        section_titles = [
            'Getting Started', 'Core Concepts', 'Intermediate Topics',
            'Advanced Techniques', 'Real-World Projects', 'Assessment & Review',
        ]
        lesson_type_pool = ['video', 'video', 'video', 'text', 'quiz', 'assignment']
        all_lessons = []
        for lc in lms_courses:
            for s_idx, s_title in enumerate(
                random.sample(section_titles, k=random.randint(3, 5))
            ):
                section = LessonSection.objects.create(
                    course=lc, title=s_title,
                    description=fake.text(max_nb_chars=200),
                    display_order=s_idx, is_active=True,
                )
                for l_idx in range(random.randint(3, 7)):
                    ltype = random.choice(lesson_type_pool)
                    # Use the provided embed codes for video lessons
                    video_embed = random.choice(EMBED_CODES) if ltype == 'video' else ''
                    lesson = Lesson.objects.create(
                        course=lc, section=section,
                        title=f"{s_title} – Part {l_idx + 1}: {fake.catch_phrase()}",
                        lesson_type=ltype,
                        description=fake.text(max_nb_chars=300),
                        content=fake.text(max_nb_chars=1000),
                        video_url=video_embed,
                        video_duration_minutes=random.randint(8, 45) if ltype == 'video' else 0,
                        is_preview=(l_idx == 0),
                        is_active=True,
                        display_order=l_idx,
                    )
                    all_lessons.append(lesson)

        # ── 22. ENROLLMENTS ──────────────────────────────────────────────────
        self.stdout.write("🎓 Creating enrollments...")
        enrollments = []
        for student in verified_students:
            for lc in random.sample(lms_courses, k=random.randint(2, 7)):
                status = random.choice(['active', 'active', 'completed', 'dropped'])
                progress = Decimal(str(round(random.uniform(0, 100), 2)))
                enr = Enrollment.objects.create(
                    student=student, course=lc,
                    enrolled_by=random.choice(users['admins']),
                    progress_percentage=progress,
                    completed_lessons=random.randint(0, 20),
                    current_grade=Decimal(str(round(random.uniform(40, 100), 2)))
                    if progress > 30 else None,
                    status=status,
                    completed_at=timezone.now() - timedelta(days=random.randint(1, 60))
                    if status == 'completed' else None,
                    last_accessed=timezone.now() - timedelta(hours=random.randint(1, 720)),
                )
                enrollments.append(enr)

        # ── 23. LESSON PROGRESS ──────────────────────────────────────────────
        self.stdout.write("📈 Creating lesson progress records...")
        for enr in enrollments[:40]:
            course_lessons = list(enr.course.lessons.filter(is_active=True))
            for lesson in random.sample(course_lessons, k=min(5, len(course_lessons))):
                is_done = random.random() > 0.4
                LessonProgress.objects.get_or_create(
                    enrollment=enr, lesson=lesson,
                    defaults=dict(
                        is_completed=is_done,
                        completion_percentage=Decimal('100.00') if is_done
                        else Decimal(str(round(random.uniform(10, 90), 2))),
                        time_spent_minutes=random.randint(5, 60),
                        video_progress_seconds=random.randint(0, 2700),
                        started_at=timezone.now() - timedelta(days=random.randint(1, 30)),
                        completed_at=timezone.now() - timedelta(days=random.randint(0, 10))
                        if is_done else None,
                    )
                )

        # ── 24. ASSIGNMENTS ──────────────────────────────────────────────────
        self.stdout.write("📝 Creating assignments...")
        assignments = []
        for lesson in random.sample(all_lessons, k=min(40, len(all_lessons))):
            if lesson.lesson_type in ['video', 'text']:
                a = Assignment.objects.create(
                    lesson=lesson,
                    title=f"Assignment: {fake.catch_phrase()}",
                    description=fake.text(max_nb_chars=400),
                    instructions=fake.text(max_nb_chars=300),
                    max_score=Decimal('100.00'),
                    passing_score=Decimal(str(random.choice([50, 60, 70]))),
                    due_date=timezone.now() + timedelta(days=random.randint(7, 60)),
                    allow_late_submission=random.choice([True, False]),
                    late_penalty_percent=random.choice([0, 10, 20]),
                    is_active=True,
                    display_order=len(assignments),
                )
                assignments.append(a)

        # ── 25. ASSIGNMENT SUBMISSIONS ───────────────────────────────────────
        self.stdout.write("📤 Creating assignment submissions...")
        for assignment in random.sample(assignments, k=min(30, len(assignments))):
            enrolled = list(
                Enrollment.objects.filter(course=assignment.lesson.course, status='active')
            )
            for enr in random.sample(enrolled, k=min(5, len(enrolled))):
                status_choices = ['submitted', 'graded', 'returned', 'draft']
                sub_status = random.choice(status_choices)
                grader = random.choice(users['instructors'])
                AssignmentSubmission.objects.get_or_create(
                    assignment=assignment, student=enr.student,
                    defaults=dict(
                        submission_text=fake.text(max_nb_chars=600),
                        score=Decimal(str(round(random.uniform(40, 100), 2)))
                        if sub_status == 'graded' else None,
                        feedback=fake.text(max_nb_chars=200) if sub_status == 'graded' else '',
                        graded_by=grader if sub_status == 'graded' else None,
                        graded_at=timezone.now() - timedelta(days=random.randint(1, 14))
                        if sub_status == 'graded' else None,
                        status=sub_status,
                        is_late=random.random() > 0.8,
                        submitted_at=timezone.now() - timedelta(days=random.randint(1, 30))
                        if sub_status != 'draft' else None,
                    )
                )

        # ── 26. QUIZZES ──────────────────────────────────────────────────────
        self.stdout.write("🎯 Creating quizzes...")
        quizzes = []
        for lesson in random.sample(all_lessons, k=min(35, len(all_lessons))):
            if lesson.lesson_type in ['video', 'text', 'quiz']:
                quiz = Quiz.objects.create(
                    lesson=lesson,
                    title=f"Quiz: {fake.catch_phrase()}",
                    description=fake.text(max_nb_chars=200),
                    instructions=fake.text(max_nb_chars=150),
                    time_limit_minutes=random.choice([15, 20, 30, 45, None]),
                    passing_score=Decimal(str(random.choice([60, 70, 75]))),
                    max_attempts=random.randint(2, 5),
                    shuffle_questions=random.choice([True, False]),
                    show_correct_answers=random.choice([True, False]),
                    is_active=True,
                    display_order=len(quizzes),
                )
                quizzes.append(quiz)

        # ── 27. QUIZ QUESTIONS & ANSWERS ─────────────────────────────────────
        self.stdout.write("❔ Creating quiz questions and answers...")
        for quiz in quizzes:
            for i in range(random.randint(5, 12)):
                qtype = random.choice(
                    ['multiple_choice', 'multiple_choice', 'true_false', 'short_answer']
                )
                q = QuizQuestion.objects.create(
                    quiz=quiz, question_type=qtype,
                    question_text=fake.sentence() + '?',
                    explanation=fake.text(max_nb_chars=150) if random.random() > 0.4 else '',
                    points=Decimal(str(random.choice([1, 2, 5]))),
                    display_order=i, is_active=True,
                )
                if qtype == 'multiple_choice':
                    correct_idx = random.randint(0, 3)
                    for j in range(4):
                        QuizAnswer.objects.create(
                            question=q,
                            answer_text=fake.sentence(nb_words=6),
                            is_correct=(j == correct_idx),
                            display_order=j,
                        )
                elif qtype == 'true_false':
                    correct = random.choice([True, False])
                    QuizAnswer.objects.create(
                        question=q, answer_text='True',
                        is_correct=correct, display_order=0,
                    )
                    QuizAnswer.objects.create(
                        question=q, answer_text='False',
                        is_correct=not correct, display_order=1,
                    )

        # ── 28. QUIZ ATTEMPTS & RESPONSES ────────────────────────────────────
        self.stdout.write("🎯 Creating quiz attempts and responses...")
        for quiz in random.sample(quizzes, k=min(len(quizzes), 40)):
            enrolled = list(
                Enrollment.objects.filter(course=quiz.lesson.course, status='active')
            )
            for enr in random.sample(enrolled, k=min(4, len(enrolled))):
                for _ in range(random.randint(1, 2)):
                    pct = Decimal(str(round(random.uniform(40, 100), 2)))
                    attempt = QuizAttempt.objects.create(
                        quiz=quiz, student=enr.student,
                        score=pct, max_score=Decimal('100.00'), percentage=pct,
                        is_completed=True,
                        passed=pct >= quiz.passing_score,
                        completed_at=timezone.now() - timedelta(days=random.randint(1, 30)),
                        time_taken_minutes=random.randint(5, quiz.time_limit_minutes or 45),
                    )
                    for q in quiz.questions.all():
                        answers = list(q.answers.all())
                        if answers:
                            sel = random.choice(answers)
                            QuizResponse.objects.get_or_create(
                                attempt=attempt, question=q,
                                defaults=dict(
                                    selected_answer=sel,
                                    text_response='',
                                    is_correct=sel.is_correct,
                                    points_earned=q.points if sel.is_correct else Decimal('0.00'),
                                )
                            )

        # ── 29. REVIEWS ──────────────────────────────────────────────────────
        self.stdout.write("⭐ Creating reviews...")
        for lc in lms_courses:
            enrolled = list(Enrollment.objects.filter(course=lc))
            for enr in random.sample(enrolled, k=min(random.randint(3, 10), len(enrolled))):
                Review.objects.get_or_create(
                    course=lc, student=enr.student,
                    defaults=dict(
                        rating=random.randint(3, 5),
                        review_text=fake.text(max_nb_chars=400),
                        is_approved=random.random() > 0.1,
                    )
                )

        # ── 30. CERTIFICATES ─────────────────────────────────────────────────
        self.stdout.write("🏆 Creating certificates...")
        completed = [
            e for e in enrollments if e.status == 'completed' and e.course.has_certificate
        ]
        for enr in completed:
            Certificate.objects.get_or_create(
                student=enr.student, course=enr.course,
                defaults=dict(
                    completion_date=(enr.completed_at or timezone.now()).date(),
                    grade=random.choice(['A', 'A*', 'B', 'Merit', 'Distinction']),
                    verification_code=uuid.uuid4(),
                    is_verified=True,
                )
            )

        # ── 31. TRANSACTIONS ─────────────────────────────────────────────────
        self.stdout.write("💳 Creating transactions...")
        for student in verified_students:
            for _ in range(random.randint(2, 6)):
                gw = random.choice(gateways)
                amt = Decimal(str(round(random.uniform(50, 300), 2)))
                status = random.choice(['pending', 'completed', 'completed', 'completed', 'failed'])
                txn_type = random.choice(['enrollment', 'subscription', 'refund'])
                Transaction.objects.create(
                    user=student, transaction_type=txn_type,
                    amount=amt, currency='USD',
                    gateway=gw,
                    gateway_transaction_id=f"{gw.slug}_{uuid.uuid4().hex[:20]}",
                    status=status,
                    course=random.choice(lms_courses) if txn_type == 'enrollment' else None,
                    metadata={
                        'payment_method': random.choice(['card', 'paypal', 'bank_transfer']),
                        'card_last4': str(random.randint(1000, 9999)),
                        'card_brand': random.choice(['Visa', 'Mastercard', 'Amex']),
                        'description': f"Payment for {fake.catch_phrase()}",
                    },
                    completed_at=timezone.now() - timedelta(days=random.randint(1, 90))
                    if status == 'completed' else None,
                )

        # ── 32. INVOICES ─────────────────────────────────────────────────────
        self.stdout.write("🧾 Creating invoices...")
        completed_txns = list(Transaction.objects.filter(status='completed'))
        for txn in random.sample(completed_txns, k=min(40, len(completed_txns))):
            subtotal = txn.amount
            Invoice.objects.create(
                student=txn.user,
                course=txn.course if txn.course else None,
                subtotal=subtotal,
                tax_rate=Decimal('5.00'),
                discount_amount=Decimal('0.00'),
                currency='USD',
                status='paid',
                due_date=(txn.completed_at + timedelta(days=30)).date()
                if txn.completed_at else timezone.now().date() + timedelta(days=30),
                paid_date=txn.completed_at.date() if txn.completed_at else None,
                notes=f"Invoice for transaction {txn.transaction_id}. Thank you for your payment.",
            )

        # ── 33. BADGES ───────────────────────────────────────────────────────
        self.stdout.write("🏅 Creating badges...")
        badge_raw = [
            ('First Course Completed', 'award', 'bronze', 10,
             'Complete your first course'),
            ('Quick Learner', 'zap', 'yellow', 20,
             'Complete a course in under 7 days'),
            ('Quiz Master', 'brain', 'purple', 15,
             'Score 100% on 5 quizzes'),
            ('Perfect Score', 'star', 'gold', 30,
             'Achieve 100% on a course final assessment'),
            ('Marathon Learner', 'flag', 'green', 25,
             'Complete 10 or more courses'),
            ('Assignment Pro', 'file-text', 'blue', 15,
             'Submit 20 assignments on time'),
            ('Community Helper', 'users', 'cyan', 20,
             'Contribute helpful replies to 10 discussions'),
            ('Early Bird', 'sunrise', 'orange', 10,
             'Complete lessons before 8 AM for 7 consecutive days'),
        ]
        badges = []
        for name, icon, color, points, criteria in badge_raw:
            badges.append(Badge.objects.create(
                name=name, icon=icon, color=color, points=points,
                criteria=criteria,
                description=f"Awarded for: {criteria.lower()}",
                is_active=True,
            ))

        # ── 34. STUDENT BADGES ────────────────────────────────────────────────
        self.stdout.write("🎖️  Awarding badges...")
        for student in verified_students:
            for badge in random.sample(badges, k=random.randint(1, 5)):
                StudentBadge.objects.get_or_create(
                    student=student, badge=badge,
                    defaults=dict(
                        awarded_by=random.choice(users['admins'] + users['instructors']),
                        reason=fake.sentence(),
                    )
                )

        # ── 35. BLOG CATEGORIES ───────────────────────────────────────────────
        self.stdout.write("📰 Creating blog categories...")
        blog_cat_raw = [
            ('Technology Trends', 'trending-up', 'blue'),
            ('Learning Tips', 'book-open', 'green'),
            ('Career Advice', 'briefcase', 'purple'),
            ('Student Success Stories', 'award', 'yellow'),
            ('University News', 'newspaper', 'red'),
            ('Research & Innovation', 'flask', 'cyan'),
        ]
        blog_categories = []
        for idx, (name, icon, color) in enumerate(blog_cat_raw):
            blog_categories.append(BlogCategory.objects.create(
                name=name, icon=icon, color=color,
                description=fake.text(max_nb_chars=200),
                display_order=idx, is_active=True,
            ))

        # ── 36. BLOG POSTS ────────────────────────────────────────────────────
        self.stdout.write("✍️  Creating blog posts...")
        authors = users['instructors'] + users['content_managers'] + users['admins']
        for author in authors:
            for _ in range(random.randint(1, 3)):
                status = random.choice(['published', 'published', 'draft', 'archived'])
                BlogPost.objects.create(
                    title=fake.catch_phrase(),
                    subtitle=fake.sentence(),
                    excerpt=fake.text(max_nb_chars=300),
                    content='\n\n'.join([fake.text(max_nb_chars=500) for _ in range(6)]),
                    category=random.choice(blog_categories),
                    tags=[fake.word() for _ in range(random.randint(2, 5))],
                    author=author,
                    author_name=author.get_full_name(),
                    author_title=fake.job(),
                    author_bio=fake.text(max_nb_chars=200),
                    featured_image_alt=fake.sentence(nb_words=5),
                    read_time=random.randint(3, 15),
                    views_count=random.randint(10, 5000),
                    status=status,
                    is_featured=random.random() > 0.8,
                    publish_date=timezone.now() - timedelta(days=random.randint(1, 180)),
                    meta_description=fake.text(max_nb_chars=155),
                    meta_keywords=', '.join([fake.word() for _ in range(4)]),
                )

        # ── 37. DISCUSSIONS & REPLIES ─────────────────────────────────────────
        self.stdout.write("💬 Creating discussions...")
        discussions = []
        for lc in lms_courses:
            enrolled_users = list(User.objects.filter(enrollments__course=lc))
            for _ in range(random.randint(2, 6)):
                if not enrolled_users:
                    break
                author = random.choice(enrolled_users)
                disc = Discussion.objects.create(
                    course=lc,
                    title=fake.sentence(),
                    content=fake.text(max_nb_chars=600),
                    author=author,
                    is_pinned=random.random() > 0.85,
                    is_locked=random.random() > 0.9,
                    views_count=random.randint(5, 300),
                )
                discussions.append(disc)
                repliers = [u for u in enrolled_users if u != author]
                for _ in range(random.randint(1, 8)):
                    if repliers:
                        parent_reply = DiscussionReply.objects.create(
                            discussion=disc,
                            author=random.choice(repliers),
                            content=fake.text(max_nb_chars=400),
                            is_solution=random.random() > 0.85,
                        )
                        if random.random() > 0.6 and repliers:
                            DiscussionReply.objects.create(
                                discussion=disc,
                                author=random.choice(repliers),
                                content=fake.text(max_nb_chars=200),
                                parent=parent_reply,
                                is_solution=False,
                            )

        # ── 38. STUDY GROUPS & MESSAGES ──────────────────────────────────────
        self.stdout.write("👥 Creating study groups and messages...")
        study_groups = []
        for lc in random.sample(lms_courses, k=min(6, len(lms_courses))):
            for _ in range(random.randint(1, 2)):
                creator = random.choice(verified_students + verified_instructors)
                sg = StudyGroup.objects.create(
                    name=f"{lc.title} – Study Group {uuid.uuid4().hex[:4].upper()}",
                    description=fake.text(max_nb_chars=300),
                    course=lc,
                    max_members=random.randint(6, 20),
                    is_active=True,
                    is_public=random.choice([True, False]),
                    created_by=creator,
                )
                study_groups.append(sg)
                StudyGroupMember.objects.create(
                    study_group=sg, user=creator, role='admin', is_active=True,
                )
                enrolled_ids = list(
                    Enrollment.objects.filter(course=lc).values_list('student', flat=True)
                )
                member_users = [creator]
                for sid in random.sample(
                    enrolled_ids, k=min(sg.max_members - 1, len(enrolled_ids))
                ):
                    if sid != creator.id:
                        try:
                            member_user = User.objects.get(id=sid)
                            StudyGroupMember.objects.create(
                                study_group=sg,
                                user=member_user,
                                role=random.choice(['member', 'member', 'moderator']),
                                is_active=True,
                            )
                            member_users.append(member_user)
                        except User.DoesNotExist:
                            pass

                # StudyGroupMessages — seed chat messages
                for _ in range(random.randint(3, 10)):
                    StudyGroupMessage.objects.create(
                        study_group=sg,
                        author=random.choice(member_users),
                        content=fake.text(max_nb_chars=300),
                    )

        # ── 39. MESSAGES ──────────────────────────────────────────────────────
        self.stdout.write("✉️  Creating messages...")
        for user in verified_all:
            others = [u for u in all_users if u != user]
            for _ in range(random.randint(2, 5)):
                recipient = random.choice(others)
                is_read = random.choice([True, False])
                msg = Message.objects.create(
                    sender=user, recipient=recipient,
                    subject=fake.sentence(),
                    body=fake.text(max_nb_chars=500),
                    is_read=is_read,
                    read_at=timezone.now() - timedelta(hours=random.randint(1, 72))
                    if is_read else None,
                )
                if random.random() > 0.6:
                    Message.objects.create(
                        sender=recipient, recipient=user,
                        subject=f"Re: {msg.subject}",
                        body=fake.text(max_nb_chars=300),
                        parent=msg,
                        is_read=random.choice([True, False]),
                    )

        # ── 40. SUPPORT TICKETS ───────────────────────────────────────────────
        self.stdout.write("🎫 Creating support tickets...")
        tickets = []
        ticket_creators = (
            verified_students +
            random.sample(verified_instructors, k=min(3, len(verified_instructors)))
        )
        for creator in ticket_creators:
            for _ in range(random.randint(1, 3)):
                status = random.choice(
                    ['open', 'in_progress', 'waiting_response', 'resolved', 'closed']
                )
                ticket = SupportTicket.objects.create(
                    user=creator,
                    category=random.choice(['technical', 'account', 'course', 'payment', 'other']),
                    subject=fake.sentence(),
                    description=fake.text(max_nb_chars=600),
                    priority=random.choice(['low', 'normal', 'high', 'urgent']),
                    status=status,
                    assigned_to=random.choice(users['support']),
                    resolved_at=timezone.now() - timedelta(days=random.randint(1, 30))
                    if status in ['resolved', 'closed'] else None,
                )
                tickets.append(ticket)
                for _ in range(random.randint(1, 5)):
                    TicketReply.objects.create(
                        ticket=ticket,
                        author=random.choice([ticket.user, ticket.assigned_to]),
                        message=fake.text(max_nb_chars=400),
                        is_internal_note=random.random() > 0.75,
                    )

        # ── 41. NOTIFICATIONS ─────────────────────────────────────────────────
        self.stdout.write("🔔 Creating notifications...")
        ntypes = ['enrollment', 'assignment', 'grade', 'announcement',
                  'message', 'certificate', 'system']
        for user in verified_all:
            for _ in range(random.randint(4, 14)):
                is_read = random.choice([True, False])
                Notification.objects.create(
                    user=user,
                    notification_type=random.choice(ntypes),
                    title=fake.sentence(),
                    message=fake.text(max_nb_chars=250),
                    link=f"/courses/{random.randint(1, 10)}" if random.random() > 0.4 else '',
                    is_read=is_read,
                    read_at=timezone.now() - timedelta(hours=random.randint(1, 96))
                    if is_read else None,
                )

        # ── 42. ANNOUNCEMENTS ─────────────────────────────────────────────────
        self.stdout.write("📢 Creating announcements...")
        categories = list(CourseCategory.objects.all())
        for creator in users['admins'] + users['instructors']:
            ann_type = random.choice(['system', 'course'])
            Announcement.objects.create(
                title=fake.sentence(),
                content=fake.text(max_nb_chars=600),
                announcement_type=ann_type,
                priority=random.choice(['low', 'normal', 'high', 'urgent']),
                course=random.choice(lms_courses) if ann_type == 'course' else None,
                category=random.choice(categories) if ann_type == 'category' else None,
                created_by=creator,
                is_active=random.random() > 0.15,
                publish_date=timezone.now() - timedelta(days=random.randint(1, 90)),
                expiry_date=timezone.now() + timedelta(days=random.randint(30, 120))
                if random.random() > 0.4 else None,
            )

        # ── 43. CONTACT MESSAGES ──────────────────────────────────────────────
        self.stdout.write("📧 Creating contact messages...")
        for _ in range(30):
            responder = random.choice(users['support']) if random.random() > 0.35 else None
            ContactMessage.objects.create(
                user=random.choice(verified_students) if random.random() > 0.5 else None,
                name=fake.name(), email=fake.email(),
                subject=random.choice(
                    ['admissions', 'programs', 'campus', 'financial', 'support', 'other']
                ),
                message=fake.text(max_nb_chars=600),
                is_read=random.choice([True, False]),
                responded=responder is not None,
                responded_by=responder,
                responded_at=timezone.now() - timedelta(days=random.randint(1, 20))
                if responder else None,
                created_at=timezone.now() - timedelta(days=random.randint(1, 120)),
            )

        # ── 44. AUDIT LOGS ────────────────────────────────────────────────────
        self.stdout.write("📋 Creating audit logs...")
        actions = ['create', 'update', 'delete', 'login', 'logout',
                   'access', 'export', 'permission_change']
        model_names = ['Course', 'User', 'Enrollment', 'Assignment',
                       'Payment', 'Review', 'Discussion', 'Application']
        for user in verified_all:
            for _ in range(random.randint(4, 12)):
                AuditLog.objects.create(
                    user=user,
                    action=random.choice(actions),
                    model_name=random.choice(model_names),
                    object_id=str(random.randint(1, 200)),
                    description=fake.sentence(),
                    ip_address=fake.ipv4(),
                    user_agent=fake.user_agent(),
                    extra_data={
                        'browser': random.choice(['Chrome', 'Firefox', 'Safari', 'Edge']),
                        'platform': random.choice(['Windows', 'Mac', 'Linux', 'iOS', 'Android']),
                        'location': fake.city(),
                        'session_id': uuid.uuid4().hex,
                    },
                )

        # ── 45. BROADCAST MESSAGES ────────────────────────────────────────────
        self.stdout.write("📡 Creating broadcast messages...")
        broadcast_creators = verified_admins + verified_content
        for subject, ftype, fvals, status in [
            ('Welcome to the New Academic Year!', 'all_users', {}, 'sent'),
            ('Important: Upcoming System Maintenance', 'all_users', {}, 'sent'),
            ('Application Deadline Reminder', 'application_status',
             {'application_statuses': ['draft', 'pending_payment']}, 'sent'),
            ('Enrolment Confirmation for New Students', 'enrollment_status',
             {'enrollment_statuses': ['active']}, 'sent'),
            ('Upcoming Events Newsletter', 'all_users', {}, 'draft'),
            ('Course Update Notification for Students', 'role',
             {'roles': ['student']}, 'sent'),
        ]:
            if ftype == 'all_users':
                emails = [u.email for u in verified_all]
            elif ftype == 'role':
                role = fvals.get('roles', ['student'])[0]
                emails = [u.email for u in verified_all if u.profile.role == role]
            elif ftype == 'application_status':
                statuses = fvals.get('application_statuses', [])
                emails = list({a.email for a in applications if a.status in statuses})
            elif ftype == 'enrollment_status':
                statuses = fvals.get('enrollment_statuses', [])
                emails = list({e.student.email for e in enrollments if e.status in statuses})
            else:
                emails = []
            BroadcastMessage.objects.create(
                subject=subject, message=fake.text(max_nb_chars=500),
                filter_type=ftype, filter_values=fvals,
                recipient_emails=emails,
                recipient_count=len(emails),
                status=status,
                created_by=random.choice(broadcast_creators),
                sent_at=timezone.now() - timedelta(days=random.randint(1, 30))
                if status == 'sent' else None,
                error_message='' if status != 'failed' else 'SMTP connection timeout',
            )

        # ── 46. STAFF PAYROLL ─────────────────────────────────────────────────
        self.stdout.write("💰 Creating staff payroll records (full 12-month history)...")
        finance_admin = users['finance'][0]
        approver = users['admins'][0]
        for staff in staff_users:
            for month in range(1, 13):
                base = Decimal(str(round(random.uniform(2500, 8000), 2)))
                allowances = Decimal(str(round(random.uniform(200, 1200), 2)))
                bonuses = Decimal(str(round(random.uniform(0, 1000), 2)))
                tax = Decimal(str(round(float(base + allowances + bonuses) * 0.2, 2)))
                other_ded = Decimal(str(round(random.uniform(50, 300), 2)))
                pstatus = random.choice(['paid', 'paid', 'paid', 'pending', 'processing'])
                StaffPayroll.objects.create(
                    staff=staff,
                    month=month,
                    year=2025,
                    base_salary=base,
                    allowances=allowances,
                    bonuses=bonuses,
                    tax_deduction=tax,
                    other_deductions=other_ded,
                    payment_status=pstatus,
                    payment_method=random.choice(
                        ['bank_transfer', 'check', 'mobile_money']
                    ),
                    payment_date=date(2025, month, random.randint(25, 28))
                    if pstatus == 'paid' else None,
                    bank_name=random.choice(
                        ['Barclays', 'HSBC', 'Lloyds', 'NatWest', 'Santander']
                    ),
                    account_number=str(random.randint(10_000_000, 99_999_999)),
                    notes=(
                        f"Monthly payroll for "
                        f"{date(2025, month, 1).strftime('%B %Y')}. "
                        f"Processed by finance team."
                    ),
                    created_by=finance_admin,
                    approved_by=approver if pstatus == 'paid' else None,
                    approved_at=timezone.now() - timedelta(days=random.randint(1, 28))
                    if pstatus == 'paid' else None,
                )

        # ── 47. LIBRARY ITEMS ─────────────────────────────────────────────────
        self.stdout.write("📚 Creating library items...")
        library_raw = [
            # title, author, item_type, isbn, year, faculty_idx, description
            ('Introduction to Algorithms', 'Cormen, Leiserson, Rivest, Stein', 'book',
            '9780262046305', 2022, 0,
            'The definitive reference for algorithms and data structures. Required text for CS students.'),
            ('Clean Code: A Handbook of Agile Software Craftsmanship', 'Robert C. Martin', 'book',
            '9780132350884', 2008, 0,
            'Best practices for writing maintainable, readable code in any language.'),
            ('Deep Learning', 'Goodfellow, Bengio, Courville', 'book',
            '9780262035613', 2016, 0,
            'Comprehensive coverage of deep learning theory and modern neural network architectures.'),
            ('The Pragmatic Programmer', 'Hunt & Thomas', 'book',
            '9780135957059', 2019, 0,
            'Timeless software development wisdom for programmers at every level.'),
            ('Python Crash Course', 'Eric Matthes', 'book',
            '9781718502703', 2023, 0,
            'Hands-on, project-based introduction to Python programming.'),
            ('Design Patterns: Elements of Reusable OO Software', 'Gang of Four', 'book',
            '9780201633610', 1994, 0,
            'The classic reference for software design patterns used throughout the industry.'),
            ('Structural Analysis', 'Russell C. Hibbeler', 'book',
            '9780134610672', 2020, 1,
            'Comprehensive coverage of structural mechanics for civil and structural engineering.'),
            ('Fundamentals of Electric Circuits', 'Alexander & Sadiku', 'book',
            '9780078028229', 2020, 1,
            'Essential textbook for electrical circuit analysis with worked examples.'),
            ('Engineering Mechanics: Statics', 'R.C. Hibbeler', 'book',
            '9780133918922', 2019, 1,
            'Core mechanics text covering forces, equilibrium, and structural analysis.'),
            ('Soil Mechanics and Foundations', 'Muni Budhu', 'book',
            '9781119600343', 2019, 1,
            'Comprehensive geotechnical engineering reference for civil engineering students.'),
            ('Principles of Corporate Finance', 'Brealey, Myers, Allen', 'book',
            '9781260565553', 2022, 2,
            'Authoritative corporate finance text used in MBA programmes worldwide.'),
            ('Financial Accounting', 'Weygandt, Kimmel, Kieso', 'book',
            '9781119494683', 2022, 2,
            'Core financial accounting text covering IFRS and US GAAP standards.'),
            ('Marketing Management', 'Philip Kotler & Kevin Lane Keller', 'book',
            '9780134236933', 2016, 2,
            'The leading marketing management textbook with global case studies.'),
            ('The Lean Startup', 'Eric Ries', 'book',
            '9780307887894', 2011, 2,
            'Essential reading for entrepreneurs on building and scaling startups efficiently.'),
            ('Fundamentals of Nursing', 'Taylor, Lynn, Bartlett', 'book',
            '9781975168155', 2023, 3,
            'Comprehensive nursing foundations text for pre-registration nursing students.'),
            ('Pharmacology for Nurses', 'Michael Patrick Adams', 'book',
            '9780136817093', 2022, 3,
            'Core pharmacology reference with drug classifications and nursing implications.'),
            ('Public Health: An Introduction', 'Naidoo & Wills', 'book',
            '9780230368941', 2016, 3,
            'Accessible introduction to public health concepts, policy, and practice.'),
            ('The Norton Anthology of English Literature', 'Stephen Greenblatt (ed.)', 'book',
            '9780393603071', 2018, 4,
            'Definitive anthology covering English literature from the Middle Ages to the present.'),
            ('Thinking with Type', 'Ellen Lupton', 'book',
            '9781568989693', 2010, 4,
            'Essential guide to typography for graphic designers and visual communicators.'),
            ('The Design of Everyday Things', 'Don Norman', 'book',
            '9780465050659', 2013, 4,
            'Foundational UX and product design thinking — essential for all design students.'),
            # E-Journals
            ('IEEE Transactions on Neural Networks and Learning Systems', 'IEEE', 'journal',
            '', 2024, 0,
            'Peer-reviewed journal publishing research on neural networks and learning algorithms.'),
            ('Journal of Structural Engineering', 'ASCE', 'journal',
            '', 2024, 1,
            'Leading journal covering structural analysis, design, and construction technology.'),
            ('Journal of Finance', 'American Finance Association', 'journal',
            '', 2024, 2,
            'Top-tier academic journal for financial economics research and theory.'),
            ('The Lancet', 'Elsevier', 'journal',
            '', 2024, 3,
            'Prestigious medical journal covering clinical research and global health policy.'),
            # E-Books / Digital Resources
            ('Python Documentation (Official)', 'Python Software Foundation', 'ebook',
            '', 2024, 0,
            'Complete official Python 3 documentation and tutorial library.'),
            ('MDN Web Docs', 'Mozilla Foundation', 'ebook',
            '', 2024, 0,
            'Comprehensive web development reference for HTML, CSS, and JavaScript.'),
            ('OWASP Top 10 Security Risks', 'OWASP Foundation', 'ebook',
            '', 2024, 0,
            'Industry-standard guide to the most critical web application security vulnerabilities.'),
        ]

        ITYPE_TO_CATEGORY = {
            'book': 'Books', 'journal': 'Periodicals', 'ebook': 'Other',
        }
        ITYPE_TO_SUBCATEGORY = {
            'book': 'Academic Books', 'journal': 'E-Journals', 'ebook': 'E-Books',
        }
        for idx, (title, author, itype, isbn, year, fac_idx, desc) in enumerate(library_raw):
            LibraryItem.objects.create(
                title=title,
                author=author,
                category=ITYPE_TO_CATEGORY.get(itype, 'Other'),
                subcategory=ITYPE_TO_SUBCATEGORY.get(itype, 'Other'),
                isbn=isbn,
                year=year if year else None,
                description=desc,
                access='members',
                featured=(idx < 5),
                order=idx,
                created_by=admin_user,
                is_active=True,
            )
        self.stdout.write(self.style.SUCCESS(f"   ✅ {LibraryItem.objects.count()} library items created"))

        # ── 47. EXAMS, EXAM QUESTIONS, STUDENT RESPONSES, STATUS LOGS ─────────
        self.stdout.write("📝 Creating exams, questions, responses, and status logs...")
        import datetime as dt
        import secrets as _secrets

        # Build one exam per LMS course per instructor, covering different exam types
        exam_type_pool = [
            Exam.CA, Exam.MID_SEMESTER, Exam.END_OF_SEMESTER,
            Exam.SUPPLEMENTARY, Exam.PRACTICAL,
        ]
        exam_status_pool = [
            Exam.DRAFT, Exam.SUBMITTED, Exam.APPROVED, Exam.PUBLISHED, Exam.PUBLISHED,
        ]
        created_exams = []

        for idx, lc in enumerate(lms_courses):
            instructor = lc.instructor or random.choice(users['instructors'])
            exam_type  = exam_type_pool[idx % len(exam_type_pool)]
            status     = random.choice(exam_status_pool)

            # Schedule: spread exams over coming 60 days
            exam_date  = (timezone.now() + timedelta(days=random.randint(5, 60))).date()
            start_hr   = random.choice([8, 9, 10, 11, 14, 15])
            start_time = dt.time(start_hr, 0)
            end_time   = dt.time(start_hr + 2, 0)          # 2-hour exam

            exam = Exam(
                title=f"{lc.title} — {Exam(exam_type=exam_type).get_exam_type_display()} {exam_date.year}",
                description=f"Formal {exam_type} examination for {lc.title}.",
                exam_type=exam_type,
                mode=random.choice([Exam.ONLINE, Exam.IN_PERSON, Exam.HYBRID]),
                course=lc,
                academic_session=current_session,
                department=lc.academic_course.department if lc.academic_course else None,
                instructor=instructor,
                exam_date=exam_date,
                start_time=start_time,
                end_time=end_time,
                instruction_window_minutes=10,
                venue=random.choice([
                    'Hall A', 'Hall B', 'Lecture Theatre 1',
                    'Online (LMS)', 'Computer Lab 1', 'Examination Centre',
                ]),
                hall_capacity=random.choice([50, 100, 150, 200]),
                expected_candidates=random.randint(20, 80),
                questions_per_student=random.choice([20, 25, 30, 40]),
                total_marks=Decimal(str(random.choice([50, 60, 80, 100]))),
                pass_mark=Decimal(str(random.choice([40, 45, 50]))),
                shuffle_questions=random.choice([True, False]),
                shuffle_options=random.choice([True, False]),
                show_result_immediately=lc.academic_course is None,  # True for standalone LMS courses, False for academic session courses
                instructions=(
                    "Answer all questions. No electronic devices are permitted. "
                    "Read each question carefully before answering. "
                    "Time allowed: 2 hours."
                ),
                special_instructions="Please bring your student ID card.",
                internal_notes=f"Set by {instructor.get_full_name()}. Reviewed by HOD.",
                has_accommodations=random.random() > 0.85,
                status=status,
                created_by=instructor,
                is_active=True,
            )
            # Set approval metadata based on status
            if status in (Exam.SUBMITTED, Exam.APPROVED, Exam.PUBLISHED):
                exam.submitted_by = instructor
                exam.submitted_at = timezone.now() - timedelta(days=random.randint(5, 20))
                exam.submission_count = 1
            if status in (Exam.APPROVED, Exam.PUBLISHED):
                exam.approved_by  = random.choice(users['admins'])
                exam.approved_at  = timezone.now() - timedelta(days=random.randint(1, 10))
            if status == Exam.PUBLISHED:
                exam.published_by = random.choice(users['admins'])
                exam.published_at = timezone.now() - timedelta(days=random.randint(1, 5))

            # Bypass full_clean during seeding (validation requires saved FKs)
            # Use update_or_create pattern to avoid slug collisions
            try:
                exam.save()
                created_exams.append(exam)
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"   ⚠ Skipped exam for {lc.title}: {e}"))
                continue

            # ── STATUS LOGS ───────────────────────────────────────────────────
            if status == Exam.SUBMITTED:
                ExamStatusLog(
                    exam=exam, from_status=Exam.DRAFT, to_status=Exam.SUBMITTED,
                    changed_by=instructor,
                    note="Submitted for admin review.",
                ).save()
            elif status == Exam.APPROVED:
                ExamStatusLog(
                    exam=exam, from_status=Exam.DRAFT, to_status=Exam.SUBMITTED,
                    changed_by=instructor, note="Initial submission.",
                ).save()
                ExamStatusLog(
                    exam=exam, from_status=Exam.SUBMITTED, to_status=Exam.APPROVED,
                    changed_by=random.choice(users['admins']),
                    note="Approved after review. Questions verified.",
                ).save()
            elif status == Exam.PUBLISHED:
                ExamStatusLog(
                    exam=exam, from_status=Exam.DRAFT, to_status=Exam.SUBMITTED,
                    changed_by=instructor, note="Initial submission.",
                ).save()
                ExamStatusLog(
                    exam=exam, from_status=Exam.SUBMITTED, to_status=Exam.APPROVED,
                    changed_by=random.choice(users['admins']),
                    note="Approved — questions and marking scheme verified.",
                ).save()
                ExamStatusLog(
                    exam=exam, from_status=Exam.APPROVED, to_status=Exam.PUBLISHED,
                    changed_by=random.choice(users['admins']),
                    note="Published and visible to eligible students.",
                ).save()

        self.stdout.write(self.style.SUCCESS(
            f"   ✅ {Exam.objects.count()} exams created, "
            f"{ExamStatusLog.objects.count()} status log entries"
        ))

        # ── EXAM QUESTIONS ─────────────────────────────────────────────────────
        self.stdout.write("❓ Creating exam questions...")

        def make_mcq_options(correct_index, count=4):
            """Build a well-formed options list for MCQ questions."""
            answers = [
                f"Option {chr(65 + i)}: {fake.sentence(nb_words=random.randint(3, 8))}"
                for i in range(count)
            ]
            return [
                {
                    "id":         f"opt-{uuid.uuid4().hex[:8]}",
                    "text":       answers[i],
                    "is_correct": (i == correct_index),
                }
                for i in range(count)
            ]

        def make_tf_options(correct_is_true):
            return [
                {"id": f"opt-{uuid.uuid4().hex[:8]}", "text": "True",
                 "is_correct": correct_is_true},
                {"id": f"opt-{uuid.uuid4().hex[:8]}", "text": "False",
                 "is_correct": not correct_is_true},
            ]

        for exam in created_exams:
            num_questions = random.randint(30, 50)
            diff_pool = (
                [ExamQuestion.EASY]   * 10 +
                [ExamQuestion.MEDIUM] * 15 +
                [ExamQuestion.HARD]   * 10
            )
            qtype_pool = (
                [ExamQuestion.MCQ]          * 20 +
                [ExamQuestion.TRUE_FALSE]   * 8  +
                [ExamQuestion.SHORT_ANSWER] * 5  +
                [ExamQuestion.MULTI_SELECT] * 5  +
                [ExamQuestion.ESSAY]        * 2
            )
            random.shuffle(diff_pool)
            random.shuffle(qtype_pool)

            for order in range(min(num_questions, len(diff_pool))):
                qtype = qtype_pool[order % len(qtype_pool)]
                diff  = diff_pool[order % len(diff_pool)]
                marks = Decimal(str(random.choice([1, 1, 2, 2, 3, 5])))

                if qtype == ExamQuestion.MCQ:
                    options = make_mcq_options(random.randint(0, 3))
                elif qtype == ExamQuestion.MULTI_SELECT:
                    # 2 correct out of 4
                    base = make_mcq_options(0)  # start all false
                    correct_idxs = random.sample(range(4), 2)
                    for i, o in enumerate(base):
                        o["is_correct"] = (i in correct_idxs)
                    options = base
                elif qtype == ExamQuestion.TRUE_FALSE:
                    options = make_tf_options(random.choice([True, False]))
                else:
                    options = []

                try:
                    ExamQuestion.objects.create(
                        exam=exam,
                        question_text=fake.sentence() + " Explain your answer in detail.",
                        question_type=qtype,
                        difficulty=diff,
                        marks=marks,
                        options=options,
                        accepted_answers=(
                            [fake.word(), fake.word()]
                            if qtype == ExamQuestion.SHORT_ANSWER else []
                        ),
                        explanation=fake.text(max_nb_chars=120),
                        order=order,
                        tags=[fake.word(), fake.word()],
                        source_reference=f"Past Paper {random.randint(2018, 2024)} Q{order+1}",
                        year_first_used=random.randint(2018, 2024),
                        created_by=exam.instructor,
                        is_active=True,
                    )
                except Exception as e:
                    pass  # skip clean() failures during seeding

        self.stdout.write(self.style.SUCCESS(
            f"   ✅ {ExamQuestion.objects.count()} exam questions created"
        ))

        # ── STUDENT EXAM RESPONSES ─────────────────────────────────────────────
        self.stdout.write("📋 Creating student exam responses...")
        published_exams = [e for e in created_exams if e.status == Exam.PUBLISHED]

        for exam in published_exams:
            # Pick enrolled students for this exam's course
            enrolled_students = list(
                Enrollment.objects.filter(
                    course=exam.course, status='active'
                ).values_list('student', flat=True)
            )
            if not enrolled_students:
                continue

            exam_questions = list(exam.questions.filter(is_active=True))
            if not exam_questions:
                continue

            sample_students = random.sample(
                enrolled_students, k=min(random.randint(3, 8), len(enrolled_students))
            )

            for student_id in sample_students:
                try:
                    student = User.objects.get(id=student_id)
                except User.DoesNotExist:
                    continue

                # Draw N questions for this student
                n_draw = exam.questions_per_student or len(exam_questions)
                drawn = random.sample(exam_questions, k=min(n_draw, len(exam_questions)))
                assigned_ids = [q.pk for q in drawn]

                # Shuffle option order per question for this student
                assigned_options_order = {}
                for q in drawn:
                    if q.options:
                        opt_ids = [o["id"] for o in q.options]
                        random.shuffle(opt_ids)
                        assigned_options_order[str(q.pk)] = opt_ids

                # Simulate answers
                answers = {}
                for q in drawn:
                    if q.question_type == ExamQuestion.MCQ:
                        correct_opts = [o for o in q.options if o.get("is_correct")]
                        if correct_opts:
                            # 75% chance of picking correct answer
                            if random.random() > 0.25:
                                answers[str(q.pk)] = correct_opts[0]["id"]
                            else:
                                answers[str(q.pk)] = random.choice(q.options)["id"]
                    elif q.question_type == ExamQuestion.TRUE_FALSE:
                        correct_opts = [o for o in q.options if o.get("is_correct")]
                        if correct_opts:
                            answers[str(q.pk)] = (
                                correct_opts[0]["id"] if random.random() > 0.3
                                else random.choice(q.options)["id"]
                            )
                    elif q.question_type == ExamQuestion.SHORT_ANSWER:
                        answers[str(q.pk)] = (
                            random.choice(q.accepted_answers)
                            if q.accepted_answers and random.random() > 0.3
                            else fake.sentence(nb_words=4)
                        )
                    elif q.question_type == ExamQuestion.ESSAY:
                        answers[str(q.pk)] = fake.text(max_nb_chars=300)
                    elif q.question_type == ExamQuestion.MULTI_SELECT:
                        correct_opts = [o["id"] for o in q.options if o.get("is_correct")]
                        answers[str(q.pk)] = correct_opts if random.random() > 0.3 else [
                            random.choice(q.options)["id"]
                        ]

                # Grade the MCQ/TF/multi-select answers
                question_scores = {}
                total_earned   = Decimal("0.00")
                total_possible = Decimal("0.00")
                pending_manual = 0

                for q in drawn:
                    total_possible += q.marks
                    ans = answers.get(str(q.pk))
                    if q.question_type in (ExamQuestion.MCQ, ExamQuestion.TRUE_FALSE):
                        correct_ids = {o["id"] for o in q.options if o.get("is_correct")}
                        is_correct  = bool(ans and ans in correct_ids)
                        earned      = q.marks if is_correct else Decimal("0.00")
                        total_earned += earned
                        question_scores[str(q.pk)] = {
                            "marks_awarded": float(earned),
                            "max_marks":     float(q.marks),
                            "is_correct":    is_correct,
                        }
                    elif q.question_type == ExamQuestion.MULTI_SELECT:
                        correct_ids = {o["id"] for o in q.options if o.get("is_correct")}
                        given       = set(ans) if isinstance(ans, list) else set()
                        is_correct  = given == correct_ids
                        earned      = q.marks if is_correct else Decimal("0.00")
                        total_earned += earned
                        question_scores[str(q.pk)] = {
                            "marks_awarded": float(earned),
                            "max_marks":     float(q.marks),
                            "is_correct":    is_correct,
                        }
                    else:
                        # short_answer / essay — pending manual
                        pending_manual += 1
                        question_scores[str(q.pk)] = {
                            "marks_awarded": None,
                            "max_marks":     float(q.marks),
                            "is_correct":    None,
                            "pending_manual": True,
                        }

                score_pct = (
                    (total_earned / total_possible * 100).quantize(Decimal("0.01"))
                    if total_possible > 0 else Decimal("0.00")
                )
                passed = (score_pct >= exam.pass_mark) if exam.pass_mark else None

                response_status = random.choice([
                    StudentExamResponse.SUBMITTED,
                    StudentExamResponse.SUBMITTED,
                    StudentExamResponse.GRADED,
                    StudentExamResponse.IN_PROGRESS,
                ])

                try:
                    StudentExamResponse.objects.create(
                        exam=exam,
                        student=student,
                        assigned_question_ids=assigned_ids,
                        assigned_options_order=assigned_options_order,
                        answers=answers,
                        question_scores=question_scores,
                        total_score=total_earned if response_status == StudentExamResponse.GRADED else None,
                        score_percentage=score_pct if response_status == StudentExamResponse.GRADED else None,
                        passed=passed if response_status == StudentExamResponse.GRADED else None,
                        overall_feedback=(
                            fake.text(max_nb_chars=150)
                            if response_status == StudentExamResponse.GRADED else ''
                        ),
                        graded_by=(
                            exam.instructor
                            if response_status == StudentExamResponse.GRADED else None
                        ),
                        graded_at=(
                            timezone.now() - timedelta(days=random.randint(1, 5))
                            if response_status == StudentExamResponse.GRADED else None
                        ),
                        pending_manual_count=pending_manual,
                        status=response_status,
                        instructions_opened_at=timezone.now() - timedelta(hours=random.randint(1, 48)),
                        exam_started_at=timezone.now() - timedelta(hours=random.randint(1, 47)),
                        submitted_at=(
                            timezone.now() - timedelta(hours=random.randint(1, 46))
                            if response_status in (
                                StudentExamResponse.SUBMITTED,
                                StudentExamResponse.GRADED,
                            ) else None
                        ),
                        auto_submitted=random.random() > 0.8,
                        time_spent_seconds=random.randint(1800, 7200),
                        ip_address=fake.ipv4(),
                        tab_switch_count=random.randint(0, 5),
                        invigilator_notes=(
                            fake.sentence() if random.random() > 0.7 else ''
                        ),
                    )
                except Exception as e:
                    pass  # skip unique constraint violations

        self.stdout.write(self.style.SUCCESS(
            f"   ✅ {StudentExamResponse.objects.count()} student exam responses created"
        ))

        # ── FINAL: UPDATE COURSE STATISTICS ──────────────────────────────────
        self.stdout.write("📊 Updating course statistics...")
        for lc in lms_courses:
            lc.update_statistics()

        # ── SUMMARY ───────────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS("\n" + "=" * 70))
        self.stdout.write(self.style.SUCCESS(
            "✅  SEEDING COMPLETE — every table, every field populated"
        ))
        self.stdout.write(self.style.SUCCESS("=" * 70))
        rows = [
            ("SiteConfig",              SiteConfig.objects.count()),
            ("History Milestones",      SiteHistoryMilestone.objects.count()),
            ("Testimonials",            Testimonial.objects.count()),
            ("Institution Members",     InstitutionMember.objects.count()),
            ("Countries",               ListOfCountry.objects.count()),
            ("Users",                   User.objects.count()),
            ("Vendors",                 Vendor.objects.count()),
            ("System Configurations",   SystemConfiguration.objects.count()),
            ("Payment Gateways",        PaymentGateway.objects.count()),
            ("Subscription Plans",      SubscriptionPlan.objects.count()),
            ("Subscriptions",           Subscription.objects.count()),
            ("Faculties",               Faculty.objects.count()),
            ("Departments",             Department.objects.count()),
            ("Programs",                Program.objects.count()),
            ("Academic Sessions",       AcademicSession.objects.count()),
            ("Academic Courses",        Course.objects.count()),
            ("Course Registrations",    CourseRegistration.objects.count()),
            ("Course Grades",           CourseGrade.objects.count()),
            ("Course Intakes",          CourseIntake.objects.count()),
            ("Required Payments",       AllRequiredPayments.objects.count()),
            ("Applications",            CourseApplication.objects.count()),
            ("Application Documents",   ApplicationDocument.objects.count()),
            ("Application Payments",    ApplicationPayment.objects.count()),
            
            ("LMS Courses",             LMSCourse.objects.count()),
            ("Lesson Sections",         LessonSection.objects.count()),
            ("Lessons",                 Lesson.objects.count()),
            ("Enrollments",             Enrollment.objects.count()),
            ("Lesson Progress",         LessonProgress.objects.count()),
            ("Assignments",             Assignment.objects.count()),
            ("Submissions",             AssignmentSubmission.objects.count()),
            ("Quizzes",                 Quiz.objects.count()),
            ("Quiz Questions",          QuizQuestion.objects.count()),
            ("Quiz Attempts",           QuizAttempt.objects.count()),
            ("Reviews",                 Review.objects.count()),
            ("Certificates",            Certificate.objects.count()),
            ("Transactions",            Transaction.objects.count()),
            ("Invoices",                Invoice.objects.count()),
            ("Badges",                  Badge.objects.count()),
            ("Student Badges",          StudentBadge.objects.count()),
            ("Blog Categories",         BlogCategory.objects.count()),
            ("Blog Posts",              BlogPost.objects.count()),
            ("Discussions",             Discussion.objects.count()),
            ("Discussion Replies",      DiscussionReply.objects.count()),
            ("Study Groups",            StudyGroup.objects.count()),
            ("Study Group Members",     StudyGroupMember.objects.count()),
            ("Study Group Messages",    StudyGroupMessage.objects.count()),
            ("Messages",                Message.objects.count()),
            ("Support Tickets",         SupportTicket.objects.count()),
            ("Ticket Replies",          TicketReply.objects.count()),
            ("Notifications",           Notification.objects.count()),
            ("Announcements",           Announcement.objects.count()),
            ("Contact Messages",        ContactMessage.objects.count()),
            ("Audit Logs",              AuditLog.objects.count()),
            ("Broadcast Messages",      BroadcastMessage.objects.count()),
            ("Staff Payrolls",          StaffPayroll.objects.count()),
            ("Fee Payments",            FeePayment.objects.count()),
            ("Library Items",           LibraryItem.objects.count()),
            ("Exams",                   Exam.objects.count()),
            ("Exam Questions",          ExamQuestion.objects.count()),
            ("Student Exam Responses",  StudentExamResponse.objects.count()),
            ("Exam Status Logs",        ExamStatusLog.objects.count()),
        ]
        for label, count in rows:
            self.stdout.write(f"   {label:<36} {count}")
        self.stdout.write(self.style.SUCCESS("=" * 70 + "\n"))