"""
Seed the database with realistic Abraytech data: a handful of tech-training
Faculties/Departments/Programs/Courses, a few flagship LMS courses with
lessons, and exactly one user per role (student/instructor/admin/support/
finance) sharing one password, so the flat course-catalog flow can be
demoed end to end without hand-building fixtures.

Idempotent: safe to re-run — existing rows are matched by their unique
keys (code/username/email) and updated in place rather than duplicated.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from pathlib import Path

from django.apps import apps as django_apps

from apps.store.models import Product, ProductCategory, ProductSpecification, ProductVariant, MediaAsset, ProductImage
from apps.eduweb.models import (
    Course,
    CourseApplication,
    CourseRegistration,
    Department,
    Enrollment,
    Faculty,
    Lesson,
    LMSCourse,
    Program,
    UserProfile,
    BlogCategory,
    BlogPost,
    ConsultationRequest,
    Industry,
    InstitutionMember,
    InstitutionPartner,
    InstitutionalSubscription,
    JobListing,
    ListOfCountry,
    NewsletterSubscriber,
    Project,
    Service,
    SiteConfig,
    SiteHistoryMilestone,
    SystemConfiguration,
    Testimonial,
    Vendor,
    Announcement,
    Assignment,
    AssignmentSubmission,
    AuditLog,
    Badge,
    Certificate,
    CourseCategory,
    CourseGrade,
    Exam,
    ExamQuestion,
    ExamStatusLog,
    LessonProgress,
    LessonSection,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizQuestion,
    QuizResponse,
    StudentBadge,
    StudentExamResponse,
    AllRequiredPayments,
    ApplicationPayment,
    FeePayment,
    Invoice,
    PaymentGateway,
    StaffPayroll,
    Subscription,
    SubscriptionPlan,
    Transaction,
    BroadcastMessage,
    ContactMessage,
    Discussion,
    DiscussionReply,
    Message,
    Notification,
    Review,
    StudyGroup,
    StudyGroupMember,
    StudyGroupMessage,
    SupportTicket,
    TicketReply,
    ApplicationDocument,
    LibraryItem,
    StaffPermissionsMatrix,
)

SEED_PASSWORD = "Abraytech@2026"


class Command(BaseCommand):
    help = "Seed realistic Abraytech demo data (faculties/programs/courses/LMS content + one user per role)."

    @transaction.atomic
    def handle(self, *args, **options):
        faculties = self._seed_faculties()
        departments = self._seed_departments(faculties)
        programs = self._seed_programs(departments)
        courses = self._seed_courses(programs)
        instructor, admin, support, finance, student_user, lms_courses = self._seed_users(programs, courses)

        self._seed_marketing_content(instructor, admin)
        self._seed_academic_extras(instructor, admin, student_user, courses, lms_courses)
        self._seed_financials(admin, instructor, support, finance, student_user, programs, lms_courses)
        self._seed_community(admin, instructor, support, student_user, lms_courses)
        self._seed_misc(student_user, courses)

        self.stdout.write(self.style.SUCCESS("\nSeed complete."))
        self.stdout.write(self.style.SUCCESS(f"Shared password for every seeded user: {SEED_PASSWORD}"))

    # ── Marketing / front-site content ──────────────────────────────────────
    def _seed_marketing_content(self, instructor, admin):
        site_config, _ = SiteConfig.objects.get_or_create(
            pk=1,
            defaults={
                "school_name": "Abraytech",
                "school_short_name": "Abraytech",
                "tagline": "Building Digital Solutions for a Smarter Future.",
                "theme_color": "#0ea5e9",
                "email": "hello@abraytech.com",
                "phone_primary": "+1 (302) 555-0142",
                "phone_ng_primary": "+234 801 234 5678",
                "whatsapp": "2348012345678",
                "email_admissions": "admissions@abraytech.com",
                "email_info": "hello@abraytech.com",
                "email_international": "global@abraytech.com",
                "phone_admissions": "+234 801 234 5679",
                "phone_general": "+1 (302) 555-0142",
                "address_usa": "8 The Green, Suite 4000, Dover, DE 19901, USA",
                "address_nigeria": "12 Admiralty Way, Lekki Phase 1, Lagos, Nigeria",
                "facebook": "https://facebook.com/abraytech",
                "instagram": "https://instagram.com/abraytech",
                "youtube": "https://youtube.com/@abraytech",
                "twitter": "https://twitter.com/abraytech",
                "linkedin": "https://linkedin.com/company/abraytech",
                "footer_tagline": (
                    "Abraytech delivers software, cybersecurity, AI, data and digital "
                    "transformation solutions that help businesses innovate, operate "
                    "securely and grow — and we train the next generation of engineers "
                    "to build it all."
                ),
                "copyright_year": "2026",
                "meta_description": (
                    "Abraytech is a technology company delivering software development, "
                    "cybersecurity, AI, IT consulting and training to clients worldwide."
                ),
                "meta_keywords": "software development, cybersecurity, AI, data, IT consulting, technology training",
                "about_mission": (
                    "To deliver reliable, well-engineered technology services and make "
                    "high-quality technical training accessible to everyone we work with."
                ),
                "about_vision": (
                    "To be a trusted technology partner known for engineering quality, "
                    "security-mindedness, and practical, outcome-driven work."
                ),
                "about_values": [
                    "Engineering Excellence", "Security by Default",
                    "Practical, Outcome-Driven Work", "Continuous Learning",
                ],
            },
        )
        self.stdout.write("Seeded SiteConfig.")

        milestones = [
            (2019, "Founding", "Abraytech is founded in Lagos, Nigeria, delivering custom software for early clients."),
            (2020, "First Enterprise Client", "Abraytech lands its first enterprise cybersecurity engagement."),
            (2021, "Training Academy Launches", "Abraytech opens its technical training academy, starting with a Full-Stack Software Engineering cohort."),
            (2023, "US Expansion", "Abraytech opens a US office to serve clients across North America."),
            (2025, "AI & Data Practice", "Abraytech launches a dedicated AI & Data engineering practice."),
        ]
        for year, title, desc in milestones:
            SiteHistoryMilestone.objects.update_or_create(
                site=site_config, year=year, title=title,
                defaults={"description": desc, "is_active": True},
            )
        self.stdout.write(f"Seeded {len(milestones)} SiteHistoryMilestone rows.")

        services_data = [
            ("Custom Software Development", "Bespoke web and mobile applications built for how your business actually works.", "code"),
            ("Cybersecurity & Penetration Testing", "Find and fix vulnerabilities before attackers do.", "shield"),
            ("AI & Data Engineering", "Data pipelines, analytics and machine learning that drive real decisions.", "brain-circuit"),
            ("Cloud Migration & DevOps", "Move to the cloud and automate delivery with confidence.", "cloud"),
            ("IT Consulting & Strategy", "Technology roadmaps and architecture reviews for growing teams.", "compass"),
            ("Mobile App Development", "Native and cross-platform apps for iOS and Android.", "smartphone"),
            ("Managed IT Support", "Ongoing infrastructure monitoring and support so your team can focus on the business.", "life-buoy"),
            ("Security Audits & Compliance", "Independent audits against SOC 2, ISO 27001 and industry best practice.", "clipboard-check"),
            ("Data Analytics & Business Intelligence", "Dashboards and reporting that turn raw data into decisions.", "bar-chart-3"),
            ("Technical Training & Upskilling", "Job-ready software, security and data training for individuals and teams.", "graduation-cap"),
        ]
        services = {}
        for title, summary, icon in services_data:
            obj, _ = Service.objects.update_or_create(
                title=title, defaults={"summary": summary, "icon": icon, "is_active": True},
            )
            services[title] = obj
        self.stdout.write(f"Seeded {len(services_data)} Service rows.")

        industries_data = [
            ("Financial Services", "Payments, banking and fintech platforms built for security and scale."),
            ("Healthcare", "Systems that handle sensitive health data with the compliance it demands."),
            ("E-commerce & Retail", "Storefronts, checkout and logistics integrations that hold up under real traffic."),
            ("Education", "Learning platforms and admissions systems for schools and training providers."),
            ("Logistics & Supply Chain", "Tracking, routing and inventory systems for physical operations."),
            ("Government & Public Sector", "Citizen-facing digital services built to public-sector standards."),
        ]
        industries = {}
        for order, (title, summary) in enumerate(industries_data, start=1):
            obj, _ = Industry.objects.update_or_create(
                title=title, defaults={"summary": summary, "order": order, "is_active": True},
            )
            industries[title] = obj
        self.stdout.write(f"Seeded {len(industries_data)} Industry rows.")

        projects_data = [
            ("Payment Gateway Modernization", "Rebuilt a fintech startup's core payment processing for reliability at scale.", "", "Financial Services", "Custom Software Development"),
            ("Cloud Migration for a Regional Healthcare Provider", "Migrated on-premise patient systems to a compliant cloud environment.", "", "Healthcare", "Cloud Migration & DevOps"),
            ("Security Audit & Hardening for an E-commerce Platform", "Found and closed critical vulnerabilities ahead of a major sales season.", "", "E-commerce & Retail", "Cybersecurity & Penetration Testing"),
            ("Custom LMS Platform for a Training Institute", "Built a bespoke learning platform to replace three disconnected tools.", "", "Education", "Custom Software Development"),
            ("Data Pipeline & Analytics Dashboard for a Logistics Company", "Real-time visibility into fleet and warehouse operations.", "", "Logistics & Supply Chain", "AI & Data Engineering"),
            ("Mobile Banking App for a Microfinance Bank", "Launched a mobile-first banking experience for underserved customers.", "", "Financial Services", "Mobile App Development"),
        ]
        for order, (title, summary, client, industry_title, service_title) in enumerate(projects_data, start=1):
            Project.objects.update_or_create(
                title=title,
                defaults={
                    "summary": summary,
                    "client_name": client,
                    "industry": industries.get(industry_title),
                    "service": services.get(service_title),
                    "challenge": f"The client needed to solve: {summary.lower()}",
                    "solution_text": f"Abraytech's team designed and delivered a solution addressing this need end to end.",
                    "results": "Delivered on time, with measurable improvements in reliability and performance.",
                    "is_featured": order <= 3,
                    "is_active": True,
                    "order": order,
                },
            )
        self.stdout.write(f"Seeded {len(projects_data)} Project rows.")

        # Store categories — created up front so products can be assigned one.
        category_defs = [
            ("Laptops", "laptop", "Ultrabooks and workstation-class laptops."),
            ("Smartphones", "smartphone", "Android smartphones across budget and flagship tiers."),
            ("Wireless Audio", "headphones", "True-wireless earbuds and headsets."),
            ("Wearables", "watch", "Smartwatches and fitness trackers."),
            ("Peripherals", "keyboard", "Keyboards, mice, and other desk accessories."),
            ("Tablets", "tablet", "Android tablets for media, note-taking, and light work."),
            ("Monitors", "monitor", "External displays for desks and multi-monitor setups."),
            ("Networking", "wifi", "Routers and other home/office networking gear."),
            ("Storage", "hard-drive", "External SSDs and other portable storage."),
            ("Power & Charging", "battery-charging", "Power banks, chargers, and charging accessories."),
            ("Apparel", "shirt", "Branded hoodies, t-shirts, and other wearables."),
            ("Bags & Accessories", "briefcase", "Backpacks, sleeves, and everyday carry gear."),
        ]
        categories = {}
        for title, icon, description in category_defs:
            categories[title], _ = ProductCategory.objects.update_or_create(
                title=title, defaults={"icon": icon, "description": description},
            )
        self.stdout.write(f"Seeded {len(category_defs)} ProductCategory rows.")

        # Gadget catalog — realistic Nigerian retail pricing (NGN, inclusive
        # of the import/logistics markup real Nigerian electronics retailers
        # charge, not a raw USD/NGN spot-rate conversion), one real photo per
        # product (apps/store/seed_images/, sourced from Wikimedia Commons —
        # see apps/store/seed_images/ATTRIBUTION.md), and a small spec sheet
        # each for the product-detail page's "Technical Details" table.
        products_data = [
            {
                "title": "Apex Pro 14 Ultrabook", "sku": "ABX-APEX14", "brand": "Apex",
                "category": "Laptops", "image": "apex_pro_14_ultrabook.jpg",
                "summary": "A 14-inch ultrabook built for engineers who live in their laptop.",
                "description": "The Apex Pro 14 pairs a 13th-Gen Intel Core i7 with 16GB of RAM and a 512GB "
                                "NVMe SSD in a 1.3kg magnesium-alloy chassis — fast enough for local dev "
                                "environments and containers, light enough to carry all day.",
                "price": Decimal("1450000.00"), "compare_at_price": None, "stock_quantity": 14,
                "specs": [("Screen", "14-inch FHD+, 400 nits"), ("Processor", "Intel Core i7 (13th Gen)"),
                          ("RAM", "16GB LPDDR5"), ("Storage", "512GB NVMe SSD"), ("Weight", "1.3 kg")],
            },
            {
                "title": "Vector 16 Pro Laptop", "sku": "ABX-VEC16", "brand": "Vector",
                "category": "Laptops", "image": "vector_16_pro_laptop.jpg",
                "summary": "A 16-inch workstation laptop for heavier builds, VMs, and multitasking.",
                "description": "The Vector 16 Pro steps up to an Intel Core i9, 32GB of RAM, and a 1TB SSD "
                                "on a 16-inch QHD display — built for anyone running multiple VMs, large "
                                "monorepos, or a Docker stack alongside a full IDE.",
                "price": Decimal("2100000.00"), "compare_at_price": Decimal("2350000.00"), "stock_quantity": 9,
                "specs": [("Screen", "16-inch QHD, 165Hz"), ("Processor", "Intel Core i9 (13th Gen)"),
                          ("RAM", "32GB DDR5"), ("Storage", "1TB NVMe SSD"), ("Weight", "1.9 kg")],
            },
            {
                "title": "Nova X12 Smartphone", "sku": "ABX-NOVAX12", "brand": "Nova",
                "category": "Smartphones", "image": "nova_x12_smartphone.jpg",
                "summary": "A dependable mid-range Android phone with all-day battery life.",
                "description": "The Nova X12 covers the essentials well: a bright 6.5-inch AMOLED display, "
                                "128GB of storage, and a 5000mAh battery that comfortably lasts a full day "
                                "of calls, browsing, and mobile money apps.",
                "price": Decimal("520000.00"), "compare_at_price": Decimal("580000.00"), "stock_quantity": 26,
                "specs": [("Display", "6.5-inch AMOLED, 90Hz"), ("RAM", "8GB"), ("Storage", "128GB"),
                          ("Battery", "5000mAh"), ("Camera", "50MP main + 8MP ultrawide")],
            },
            {
                "title": "Pulse Edge Smartphone", "sku": "ABX-PULSE", "brand": "Pulse",
                "category": "Smartphones", "image": "pulse_edge_smartphone.jpg",
                "summary": "A flagship-tier phone with a faster chipset and a sharper camera stack.",
                "description": "The Pulse Edge steps up to 12GB of RAM, 256GB of storage, and a 6.7-inch "
                                "AMOLED panel, with a 5200mAh battery and 65W fast charging — ships with a "
                                "protective folio case included.",
                "price": Decimal("980000.00"), "compare_at_price": None, "stock_quantity": 11,
                "specs": [("Display", "6.7-inch AMOLED, 120Hz"), ("RAM", "12GB"), ("Storage", "256GB"),
                          ("Battery", "5200mAh, 65W fast charge"), ("In the box", "Phone + folio case")],
            },
            {
                "title": "AeroBuds Pro Wireless Earbuds", "sku": "ABX-AERO", "brand": "AeroBuds",
                "category": "Wireless Audio", "image": "aerobuds_pro_wireless_earbuds.jpg",
                "summary": "True-wireless earbuds with active noise cancellation.",
                "description": "AeroBuds Pro pack active noise cancellation, a sweat-resistant shell, and a "
                                "compact charging case rated for 32 hours of total playback — 8 hours per "
                                "charge on the earbuds alone.",
                "price": Decimal("95000.00"), "compare_at_price": Decimal("115000.00"), "stock_quantity": 42,
                "specs": [("Battery life", "8 hrs (32 hrs with case)"), ("Noise cancellation", "Active (ANC)"),
                          ("Bluetooth", "5.3"), ("Water resistance", "IPX4")],
            },
            {
                "title": "ChronoFit Smartwatch", "sku": "ABX-CHRONO", "brand": "ChronoFit",
                "category": "Wearables", "image": "chronofit_smartwatch.jpg",
                "summary": "A fitness-focused smartwatch with a week-long battery.",
                "description": "ChronoFit tracks heart rate, sleep, and workouts on a always-legible AMOLED "
                                "display, with up to 7 days of battery between charges and 5ATM water "
                                "resistance for swimming.",
                "price": Decimal("145000.00"), "compare_at_price": None, "stock_quantity": 30,
                "specs": [("Display", "1.4-inch AMOLED"), ("Battery life", "Up to 7 days"),
                          ("Water resistance", "5ATM"), ("Sensors", "Heart rate, SpO2, accelerometer")],
            },
            {
                "title": "TypeCraft Mechanical Keyboard", "sku": "ABX-TYPE-KB", "brand": "TypeCraft",
                "category": "Peripherals", "image": "typecraft_mechanical_keyboard.jpg",
                "summary": "A full-size mechanical keyboard built for long typing sessions.",
                "description": "TypeCraft uses hot-swappable blue mechanical switches on a full-size layout "
                                "with per-key RGB backlighting — satisfying tactile feedback for both code "
                                "and long-form writing.",
                "price": Decimal("68000.00"), "compare_at_price": None, "stock_quantity": 22,
                "specs": [("Switch type", "Mechanical (hot-swappable, blue)"), ("Layout", "Full-size, 104-key"),
                          ("Backlight", "Per-key RGB"), ("Connectivity", "USB-C wired")],
            },
            {
                "title": "GlideOne Wireless Mouse", "sku": "ABX-GLIDE-MS", "brand": "GlideOne",
                "category": "Peripherals", "image": "glideone_wireless_mouse.jpg",
                "summary": "A quiet, ergonomic wireless mouse for all-day desk use.",
                "description": "GlideOne pairs a comfortable ergonomic shape with silent-click switches and "
                                "a 12-month battery life on a single AA battery, connecting over a 2.4GHz "
                                "USB receiver.",
                "price": Decimal("24500.00"), "compare_at_price": None, "stock_quantity": 55,
                "specs": [("DPI", "1600"), ("Connectivity", "2.4GHz wireless"),
                          ("Battery life", "Up to 12 months (1x AA)"), ("Buttons", "3-button + scroll wheel")],
            },
            {
                "title": "Slate 10 Tablet", "sku": "ABX-SLATE10", "brand": "Slate",
                "category": "Tablets", "image": "slate_10_tablet.jpg",
                "summary": "A 10.1-inch Android tablet for streaming, reading, and note-taking.",
                "description": "The Slate 10 pairs a bright 10.1-inch display with 64GB of storage and a "
                                "long-life battery — a straightforward tablet for media, browsing, and "
                                "light productivity, expandable via microSD.",
                "price": Decimal("185000.00"), "compare_at_price": Decimal("210000.00"), "stock_quantity": 18,
                "specs": [("Display", "10.1-inch, 1920x1200"), ("RAM", "4GB"), ("Storage", "64GB, microSD expandable"),
                          ("Battery", "6800mAh")],
            },
            {
                "title": "ViewFrame 27 4K Monitor", "sku": "ABX-VIEW27", "brand": "ViewFrame",
                "category": "Monitors", "image": "viewframe_27_4k_monitor.png",
                "summary": "A 27-inch 4K monitor for code, design, and multitasking.",
                "description": "A 27-inch IPS panel at 4K resolution with USB-C and HDMI inputs and a "
                                "height-adjustable stand — enough screen real estate for a split editor "
                                "and browser, or a full design canvas.",
                "price": Decimal("310000.00"), "compare_at_price": None, "stock_quantity": 12,
                "specs": [("Screen", "27-inch IPS, 4K (3840x2160)"), ("Refresh rate", "60Hz"),
                          ("Ports", "HDMI, DisplayPort, USB-C"), ("Stand", "Height, tilt, swivel adjustable")],
            },
            {
                "title": "NetPulse Wi-Fi 6 Router", "sku": "ABX-NETPULSE", "brand": "NetPulse",
                "category": "Networking", "image": "netpulse_wifi6_router.jpg",
                "summary": "A dual-band Wi-Fi 6 router built for busy households.",
                "description": "NetPulse covers a full apartment or small office on dual-band Wi-Fi 6, with "
                                "four Gigabit LAN ports for wired devices and simple app-based setup — built "
                                "to hold up under multiple simultaneous streams and video calls.",
                "price": Decimal("62000.00"), "compare_at_price": None, "stock_quantity": 24,
                "specs": [("Wi-Fi standard", "Wi-Fi 6 (802.11ax)"), ("Bands", "Dual-band (2.4GHz + 5GHz)"),
                          ("LAN ports", "4x Gigabit"), ("Coverage", "Up to 200 sqm")],
            },
            {
                "title": "DriveVault 1TB External SSD", "sku": "ABX-VAULT1TB", "brand": "DriveVault",
                "category": "Storage", "image": "drivevault_1tb_external_ssd.jpg",
                "summary": "A pocket-sized 1TB external SSD for fast backups and file transfer.",
                "description": "DriveVault packs 1TB into a shock-resistant aluminum shell with USB-C "
                                "connectivity — fast enough for video editing scratch disks and large "
                                "backups, small enough to carry in a pocket.",
                "price": Decimal("115000.00"), "compare_at_price": Decimal("135000.00"), "stock_quantity": 20,
                "specs": [("Capacity", "1TB"), ("Interface", "USB-C 3.2"), ("Read speed", "Up to 1050 MB/s"),
                          ("Build", "Shock-resistant aluminum shell")],
            },
            {
                "title": "PowerCell 20K Power Bank", "sku": "ABX-POWER20K", "brand": "PowerCell",
                "category": "Power & Charging", "image": "powercell_20k_power_bank.jpg",
                "summary": "A 20,000mAh power bank with fast charging for phones and small laptops.",
                "description": "PowerCell 20K holds enough charge for multiple full phone top-ups, with "
                                "18W fast-charge output over USB-C and USB-A — a reliable backup for travel "
                                "or days with unreliable power.",
                "price": Decimal("32000.00"), "compare_at_price": None, "stock_quantity": 48,
                "specs": [("Capacity", "20,000mAh"), ("Output", "18W fast charge, USB-C + USB-A"),
                          ("Ports", "2 output, 1 input"), ("Weight", "380g")],
            },
            {
                "title": "BoomCube Portable Speaker", "sku": "ABX-BOOMCUBE", "brand": "BoomCube",
                "category": "Wireless Audio", "image": "boomcube_portable_speaker.jpg",
                "summary": "A compact Bluetooth speaker with surprisingly full sound.",
                "description": "BoomCube fits in one hand but fills a room, with a rechargeable battery "
                                "rated for 10 hours of playback and a durable metal grille built to handle "
                                "daily use around the house or office.",
                "price": Decimal("48000.00"), "compare_at_price": None, "stock_quantity": 33,
                "specs": [("Battery life", "Up to 10 hours"), ("Bluetooth", "5.0"),
                          ("Connectivity", "Bluetooth + AUX"), ("Weight", "540g")],
            },
            {
                # No real product photo yet — Wikimedia Commons (the source for every
                # other seed photo here) has essentially no usable, cleanly-licensed
                # apparel/bag product photography; it's an encyclopedia media
                # repository, not a stock-photo site. Shows the existing placeholder
                # icon until a real photo is uploaded via the admin.
                "title": "Abraytech Crewneck Hoodie", "sku": "ABX-HOODIE", "brand": "Abraytech",
                "category": "Apparel", "image": None,
                "summary": "A heavyweight cotton-blend hoodie with the Abraytech wordmark.",
                "description": "A 320gsm cotton-blend fleece hoodie, brushed inside for warmth, with a "
                                "kangaroo pocket and an embroidered Abraytech wordmark on the chest.",
                "price": Decimal("22000.00"), "compare_at_price": None, "stock_quantity": 40,
                "specs": [("Material", "80% cotton, 20% polyester fleece"), ("Fit", "Regular, unisex"),
                          ("Care", "Machine wash cold")],
                "variants": [("Size", "S"), ("Size", "M"), ("Size", "L"), ("Size", "XL"), ("Size", "XXL")],
            },
            {
                "title": "Abraytech Logo T-Shirt", "sku": "ABX-TSHIRT", "brand": "Abraytech",
                "category": "Apparel", "image": None,
                "summary": "A soft, breathable crewneck tee with a printed Abraytech logo.",
                "description": "A 180gsm combed-cotton crewneck tee with a screen-printed Abraytech logo on "
                                "the chest — a everyday staple, true to size.",
                "price": Decimal("8500.00"), "compare_at_price": None, "stock_quantity": 60,
                "specs": [("Material", "100% combed cotton"), ("Fit", "Regular, unisex"),
                          ("Care", "Machine wash cold")],
                "variants": [("Size", "S"), ("Size", "M"), ("Size", "L"), ("Size", "XL"), ("Size", "XXL")],
            },
            {
                "title": "TechPack 15-inch Laptop Backpack", "sku": "ABX-TECHPACK15", "brand": "TechPack",
                "category": "Bags & Accessories", "image": None,
                "summary": "A padded backpack built to carry a 15-inch laptop and a full workday.",
                "description": "A water-resistant backpack with a dedicated padded sleeve for up to a "
                                "15-inch laptop, a USB charging port on the exterior, and organizer pockets "
                                "for cables and accessories.",
                "price": Decimal("28000.00"), "compare_at_price": Decimal("34000.00"), "stock_quantity": 25,
                "specs": [("Laptop compartment", "Fits up to 15-inch"), ("Material", "Water-resistant polyester"),
                          ("Capacity", "22L"), ("Extras", "External USB charging port")],
            },
            {
                "title": "GuardSleeve 14-inch Laptop Sleeve", "sku": "ABX-GUARDSLEEVE14", "brand": "GuardSleeve",
                "category": "Bags & Accessories", "image": None,
                "summary": "A slim, shock-absorbing sleeve for 13-14-inch laptops.",
                "description": "A neoprene sleeve with a shock-absorbing foam lining and a zippered front "
                                "pocket for a charger or cables — slim enough to fit inside most backpacks.",
                "price": Decimal("9500.00"), "compare_at_price": None, "stock_quantity": 45,
                "specs": [("Fits", "13 to 14-inch laptops"), ("Material", "Neoprene with foam padding"),
                          ("Closure", "Zipper"), ("Extras", "Front accessory pocket")],
            },
        ]

        seed_images_dir = Path(django_apps.get_app_config('store').path) / 'seed_images'
        product_count = 0
        for data in products_data:
            product, _ = Product.objects.update_or_create(
                title=data["title"],
                defaults={
                    "summary": data["summary"], "description": data["description"],
                    "price": data["price"], "compare_at_price": data["compare_at_price"],
                    "currency": "NGN", "sku": data["sku"], "brand": data["brand"],
                    "category": categories[data["category"]], "stock_quantity": data["stock_quantity"],
                    "track_inventory": True, "condition": "new", "is_active": True,
                },
            )
            product_count += 1

            for sort_order, (label, value) in enumerate(data["specs"]):
                ProductSpecification.objects.update_or_create(
                    product=product, label=label, defaults={"value": value, "sort_order": sort_order},
                )

            for sort_order, (option_name, value) in enumerate(data.get("variants", [])):
                ProductVariant.objects.update_or_create(
                    product=product, option_name=option_name, value=value, defaults={"sort_order": sort_order},
                )

            # Idempotent: only attach the seed photo if this product doesn't
            # already have an image (so re-running the command never
            # re-uploads duplicate MediaAsset rows).
            if data.get("image") and not product.images.exists():
                image_path = seed_images_dir / data["image"]
                if image_path.exists():
                    asset = MediaAsset.objects.create()
                    asset.file.save(data["image"], ContentFile(image_path.read_bytes()), save=True)
                    ProductImage.objects.create(product=product, asset=asset, sort_order=0, is_primary=True)

        self.stdout.write(f"Seeded {product_count} Product rows (gadget catalog, NGN pricing).")

        jobs_data = [
            ("Full-Stack Software Engineer", "Engineering", "Lagos, Nigeria", "full_time"),
            ("Cybersecurity Analyst", "Security", "Remote", "full_time"),
            ("Data Scientist", "Data & AI", "Lagos, Nigeria", "full_time"),
            ("Cloud/DevOps Engineer", "Engineering", "Remote", "full_time"),
            ("Technical Instructor, Software Engineering", "Training", "Lagos, Nigeria", "part_time"),
            ("IT Support Specialist", "IT Operations", "Dover, DE, USA", "full_time"),
            ("Software Engineering Intern", "Engineering", "Lagos, Nigeria", "internship"),
        ]
        for title, department, location, emp_type in jobs_data:
            JobListing.objects.update_or_create(
                title=title,
                defaults={
                    "department": department, "location": location,
                    "employment_type": emp_type,
                    "description": f"We're hiring a {title.lower()} to join the Abraytech {department} team.",
                    "requirements": "Relevant experience or a completed Abraytech training track; strong communication skills.",
                    "is_active": True,
                },
            )
        self.stdout.write(f"Seeded {len(jobs_data)} JobListing rows.")

        members_data = [
            ("admin_board", "Chidinma Okafor", "Chief Executive Officer"),
            ("admin_board", "Emeka Udo", "Chief Financial Officer"),
            ("academic_board", "Tunde Bakare", "Head of Training & Curriculum"),
            ("academic_board", "Ngozi Adeyemi", "Head of Cybersecurity Practice"),
            ("advisorate_board", "Michael Reyes", "Board Advisor, Technology"),
            ("advisorate_board", "Funmi Bello", "Board Advisor, Growth"),
            ("staff", "Ada Nwosu", "Head of Customer Support"),
            ("staff", "Kelechi Eze", "Lead Cloud Engineer"),
        ]
        for member_type, name, role in members_data:
            InstitutionMember.objects.update_or_create(
                name=name, defaults={"member_type": member_type, "role": role, "is_active": True},
            )
        InstitutionMember.objects.filter(name="Chidinma Okafor").update(is_who_we_are=True)
        self.stdout.write(f"Seeded {len(members_data)} InstitutionMember rows.")

        partners_data = [
            ("Amazon Web Services (AWS) Partner Network", "partner", "Global"),
            ("Google Cloud Partner Program", "partner", "Global"),
            ("Microsoft Partner Network", "partner", "Global"),
            ("GitHub Education Partner", "affiliation", "Global"),
            ("Nigeria Computer Society", "affiliation", "Lagos, Nigeria"),
            ("ISO 27001 Certified", "accreditation", "Global"),
        ]
        for name, category, location in partners_data:
            InstitutionPartner.objects.update_or_create(
                name=name, defaults={"category": category, "location": location, "is_active": True},
            )
        self.stdout.write(f"Seeded {len(partners_data)} InstitutionPartner rows.")

        testimonials_data = [
            ("The Full-Stack Software Engineering track took me from zero coding experience to a junior developer job in six months.", "Blessing Achebe", "Full-Stack Software Engineering Graduate"),
            ("Abraytech rebuilt our checkout flow and cut our failed-payment rate in half.", "Daniel Osei", "CTO, a regional e-commerce platform"),
            ("The Cybersecurity Analyst Program is genuinely hands-on — I was doing real pentesting labs by week three.", "Samuel Igwe", "Cybersecurity Analyst Program Graduate"),
            ("Their DevOps team had us running proper CI/CD within two weeks of kickoff.", "Grace Umeh", "Engineering Manager, fintech client"),
            ("I switched careers into data science through the Data Science & Machine Learning track — best decision I've made.", "Hauwa Bello", "Data Science & Machine Learning Graduate"),
            ("Abraytech's security audit caught issues our internal team had missed for years.", "James Okonkwo", "Head of IT, healthcare client"),
            ("The instructors actually work in the industry — that made all the difference.", "Chinedu Obi", "Backend Engineering with Python & Django Graduate"),
            ("Responsive, technically excellent, and genuinely easy to work with.", "Amara Nwachukwu", "Founder, logistics startup"),
        ]
        for quote, author, role in testimonials_data:
            Testimonial.objects.update_or_create(
                author_name=author, defaults={"quote": quote, "author_role": role, "is_active": True},
            )
        self.stdout.write(f"Seeded {len(testimonials_data)} Testimonial rows.")

        blog_categories_data = [
            ("Software Engineering", "code", "blue"),
            ("Cybersecurity", "shield", "red"),
            ("AI & Data", "brain-circuit", "purple"),
            ("Cloud & DevOps", "cloud", "cyan"),
            ("Career Advice", "briefcase", "amber"),
        ]
        blog_categories = {}
        for name, icon, color in blog_categories_data:
            obj, _ = BlogCategory.objects.update_or_create(
                name=name, defaults={"icon": icon, "color": color, "is_active": True},
            )
            blog_categories[name] = obj
        self.stdout.write(f"Seeded {len(blog_categories_data)} BlogCategory rows.")

        blog_posts_data = [
            ("5 Signs Your Codebase Needs a Security Audit", "Software Engineering", "Small warning signs that are worth taking seriously before they become incidents."),
            ("What a Penetration Test Actually Involves", "Cybersecurity", "A walkthrough of how our team approaches a real engagement, start to finish."),
            ("Getting Started with Machine Learning: A Practical Path", "AI & Data", "The order we actually recommend learning ML fundamentals in."),
            ("Why We Moved to Infrastructure as Code", "Cloud & DevOps", "What changed for our delivery speed and reliability after adopting Terraform."),
            ("From Bootcamp to First Job: What Actually Helped", "Career Advice", "Lessons from our Full-Stack Software Engineering graduates who landed roles fast."),
            ("Django vs. Node.js for Your Next Backend", "Software Engineering", "A practical comparison based on projects we've shipped in both."),
            ("Building a SOC Analyst Career in 2026", "Cybersecurity", "What the role actually looks like day to day, and how to break in."),
            ("Data Visualization Mistakes That Undermine Good Analysis", "AI & Data", "Common pitfalls we see in dashboards and how to avoid them."),
        ]
        for title, category_name, excerpt in blog_posts_data:
            BlogPost.objects.update_or_create(
                title=title,
                defaults={
                    "excerpt": excerpt,
                    "content": f"{excerpt}\n\nThis is a full-length article on the topic, written by the Abraytech team.",
                    "category": blog_categories.get(category_name),
                    "author": instructor,
                    "author_name": instructor.get_full_name(),
                    "author_title": "Head of Training & Curriculum",
                    "status": "published",
                    "publish_date": timezone.now(),
                },
            )
        self.stdout.write(f"Seeded {len(blog_posts_data)} BlogPost rows.")

        consultations_data = [
            ("Ifeoma Chukwu", "ifeoma.chukwu@examplecorp.com", "ExampleCorp", "Cloud Migration & DevOps"),
            ("Robert Kim", "robert.kim@northbridge.io", "Northbridge Retail", "Cybersecurity & Penetration Testing"),
            ("Aisha Mohammed", "aisha.m@fintrust.ng", "FinTrust Microfinance", "Custom Software Development"),
            ("Peter Nwankwo", "peter@logitrack.co", "LogiTrack", "AI & Data Engineering"),
            ("Sarah Johnson", "sarah.johnson@healthfirst.org", "HealthFirst Clinics", "Security Audits & Compliance"),
        ]
        for name, email, company, service_title in consultations_data:
            ConsultationRequest.objects.update_or_create(
                email=email,
                defaults={
                    "name": name, "company": company,
                    "service_interest": services.get(service_title),
                    "message": f"We'd like to talk about {service_title.lower()} for {company}.",
                    "status": "new",
                },
            )
        self.stdout.write(f"Seeded {len(consultations_data)} ConsultationRequest rows.")

        newsletter_emails = [
            "reader1@example.com", "reader2@example.com", "reader3@example.com",
            "techfan@example.com", "hr@examplecorp.com", "founder@northbridge.io",
            "cto@fintrust.ng", "student.updates@example.com",
        ]
        for email in newsletter_emails:
            NewsletterSubscriber.objects.get_or_create(email=email)
        self.stdout.write(f"Seeded {len(newsletter_emails)} NewsletterSubscriber rows.")

        vendors_data = [
            ("Flutterwave Technology Solutions", "flutterwave-payouts@example.com", "Nigeria"),
            ("AWS Nigeria Reseller", "billing@aws-reseller.example.com", "Nigeria"),
            ("Zoom Video Communications", "billing@zoom.example.com", "USA"),
            ("GitHub, Inc.", "billing@github.example.com", "USA"),
            ("Google Workspace", "billing@google.example.com", "USA"),
        ]
        for name, email, country in vendors_data:
            Vendor.objects.update_or_create(
                name=name, defaults={"email": email, "country": country, "is_active": True},
            )
        self.stdout.write(f"Seeded {len(vendors_data)} Vendor rows.")

        institutional_subs_data = [
            ("AWS Hosting & Infrastructure", Decimal("1200.00")),
            ("GitHub Enterprise", Decimal("210.00")),
            ("Zoom Business", Decimal("150.00")),
            ("Slack Business+", Decimal("180.00")),
            ("Google Workspace", Decimal("120.00")),
        ]
        today = timezone.now().date()
        for purpose, amount in institutional_subs_data:
            InstitutionalSubscription.objects.update_or_create(
                purpose=purpose,
                defaults={
                    "amount": amount,
                    "start_date": today.replace(day=1),
                    "expiry_date": today.replace(day=1).replace(year=today.year + 1),
                    "created_by": admin,
                },
            )
        self.stdout.write(f"Seeded {len(institutional_subs_data)} InstitutionalSubscription rows.")

        system_config_data = [
            ("site_maintenance_mode", "false", "boolean", "Whether the site is in maintenance mode."),
            ("max_upload_size_mb", "25", "number", "Maximum file upload size in megabytes."),
            ("support_email", "support@abraytech.com", "text", "Primary support contact email."),
            ("admissions_open", "true", "boolean", "Whether new applications are currently being accepted."),
            ("default_currency", "USD", "text", "Default currency code for new payments."),
            ("session_timeout_minutes", "30", "number", "Inactivity timeout for logged-in sessions."),
        ]
        for key, value, setting_type, description in system_config_data:
            SystemConfiguration.objects.update_or_create(
                key=key, defaults={"value": value, "setting_type": setting_type, "description": description},
            )
        self.stdout.write(f"Seeded {len(system_config_data)} SystemConfiguration rows.")

        countries_data = [
            ("Nigeria", "NG", "234", "Nigerian"),
            ("United States", "US", "1", "American"),
            ("United Kingdom", "GB", "44", "British"),
            ("Canada", "CA", "1", "Canadian"),
            ("Ghana", "GH", "233", "Ghanaian"),
            ("Kenya", "KE", "254", "Kenyan"),
            ("South Africa", "ZA", "27", "South African"),
            ("India", "IN", "91", "Indian"),
            ("Germany", "DE", "49", "German"),
            ("France", "FR", "33", "French"),
        ]
        for country, code, phone_code, nationality in countries_data:
            ListOfCountry.objects.update_or_create(
                country=country,
                defaults={"country_code": code, "country_phonecode": phone_code, "nationality": nationality},
            )
        self.stdout.write(f"Seeded {len(countries_data)} ListOfCountry rows.")

    # ── Academic extras: categories, grades, sections/progress, assignments,
    #    quizzes, exams, certificates, badges, announcements, audit log ────────
    def _seed_academic_extras(self, instructor, admin, student_user, courses, lms_courses):
        category_data = [
            "Web Development", "Backend Engineering", "Cybersecurity",
            "Data Science", "Cloud & DevOps", "Programming Fundamentals",
        ]
        categories = {}
        for name in category_data:
            obj, _ = CourseCategory.objects.update_or_create(name=name, defaults={"is_active": True})
            categories[name] = obj
        self.stdout.write(f"Seeded {len(category_data)} CourseCategory rows.")

        # ── Lesson sections — 2 per flagship LMS course, existing lessons
        #    reassigned into "Getting Started" / "Core Concepts" ────────────────
        section_count = 0
        for code, lms in lms_courses.items():
            lessons = list(lms.lessons.order_by("display_order"))
            if not lessons:
                continue
            intro, _ = LessonSection.objects.update_or_create(
                course=lms, title="Getting Started",
                defaults={"description": "Orientation and setup.", "display_order": 1, "is_active": True},
            )
            core, _ = LessonSection.objects.update_or_create(
                course=lms, title="Core Concepts",
                defaults={"description": "The main course material.", "display_order": 2, "is_active": True},
            )
            section_count += 2
            mid = max(1, len(lessons) // 2)
            for lesson in lessons[:mid]:
                lesson.section = intro
                lesson.save(update_fields=["section"])
            for lesson in lessons[mid:]:
                lesson.section = core
                lesson.save(update_fields=["section"])
        self.stdout.write(f"Seeded {section_count} LessonSection rows.")

        # ── Lesson progress — student is further along in FSE101 (completed)
        #    than DSM101 (still in progress). ───────────────────────────────────
        progress_count = 0
        for code, done_count in (("FSE101", 4), ("DSM101", 2)):
            lms = lms_courses[code]
            enrollment = Enrollment.objects.get(student=student_user, course=lms)
            lessons = list(lms.lessons.order_by("display_order"))
            for i, lesson in enumerate(lessons):
                is_completed = i < done_count
                LessonProgress.objects.update_or_create(
                    enrollment=enrollment, lesson=lesson,
                    defaults={
                        "is_completed": is_completed,
                        "completion_percentage": Decimal("100.00") if is_completed else Decimal("40.00"),
                        "time_spent_minutes": 25 if is_completed else 10,
                    },
                )
                progress_count += 1
            if done_count == len(lessons):
                enrollment.status = "completed"
                enrollment.progress_percentage = Decimal("100.00")
                enrollment.completed_lessons = done_count
                enrollment.completed_at = timezone.now()
                enrollment.save(update_fields=["status", "progress_percentage", "completed_lessons", "completed_at"])
        self.stdout.write(f"Seeded {progress_count} LessonProgress rows.")

        # ── Assignments + one student submission per flagship course ───────────
        assignment_count = 0
        submission_count = 0
        assignments = {}
        for code, lms in lms_courses.items():
            lesson = lms.lessons.order_by("display_order").last()
            if not lesson:
                continue
            assignment, _ = Assignment.objects.update_or_create(
                lesson=lesson, title=f"{lms.title} — Practical Assignment",
                defaults={
                    "description": f"Apply what you've learned in {lms.title} to a small practical exercise.",
                    "instructions": "Submit your work as a short write-up or link to your code.",
                    "due_date": timezone.now() + timezone.timedelta(days=14),
                },
            )
            assignments[code] = assignment
            assignment_count += 1

        for code, score, status in (("FSE101", Decimal("92.00"), "graded"), ("DSM101", None, "submitted")):
            assignment = assignments[code]
            AssignmentSubmission.objects.update_or_create(
                assignment=assignment, student=student_user,
                defaults={
                    "submission_text": "Here is my completed submission for this assignment.",
                    "score": score,
                    "feedback": "Solid work — nice attention to detail." if score else "",
                    "graded_by": instructor if score else None,
                    "status": status,
                    "submitted_at": timezone.now(),
                },
            )
            submission_count += 1
        self.stdout.write(f"Seeded {assignment_count} Assignment and {submission_count} AssignmentSubmission rows.")

        # ── Quizzes + questions + answers, with two student attempts ───────────
        quiz_count = question_count = answer_count = 0
        quizzes = {}
        for code, lms in lms_courses.items():
            lesson = lms.lessons.order_by("display_order").first()
            if not lesson:
                continue
            quiz, _ = Quiz.objects.update_or_create(
                lesson=lesson, title=f"{lms.title} — Knowledge Check",
                defaults={"description": "A short check on the key ideas from this course.", "passing_score": Decimal("70.00")},
            )
            quizzes[code] = quiz
            quiz_count += 1

            mcq, _ = QuizQuestion.objects.update_or_create(
                quiz=quiz, question_text=f"Which of these is a core topic in {lms.title}?",
                defaults={"question_type": "multiple_choice", "display_order": 1, "points": Decimal("1.00")},
            )
            QuizAnswer.objects.filter(question=mcq).delete()
            QuizAnswer.objects.bulk_create([
                QuizAnswer(question=mcq, answer_text=lms.title.split(":")[0], is_correct=True, display_order=1),
                QuizAnswer(question=mcq, answer_text="Ancient History", is_correct=False, display_order=2),
                QuizAnswer(question=mcq, answer_text="Culinary Arts", is_correct=False, display_order=3),
                QuizAnswer(question=mcq, answer_text="Music Theory", is_correct=False, display_order=4),
            ])

            tf, _ = QuizQuestion.objects.update_or_create(
                quiz=quiz, question_text="Hands-on practice is part of this course.",
                defaults={"question_type": "true_false", "display_order": 2, "points": Decimal("1.00")},
            )
            QuizAnswer.objects.filter(question=tf).delete()
            QuizAnswer.objects.bulk_create([
                QuizAnswer(question=tf, answer_text="True", is_correct=True, display_order=1),
                QuizAnswer(question=tf, answer_text="False", is_correct=False, display_order=2),
            ])
            question_count += 2
            answer_count += 6

        for code in ("FSE101", "DSM101"):
            quiz = quizzes[code]
            attempt, _ = QuizAttempt.objects.update_or_create(
                quiz=quiz, student=student_user,
                defaults={
                    "score": Decimal("2.00"), "max_score": Decimal("2.00"), "percentage": Decimal("100.00"),
                    "is_completed": True, "passed": True, "completed_at": timezone.now(), "time_taken_minutes": 4,
                },
            )
            for question in quiz.questions.all():
                correct_answer = question.answers.filter(is_correct=True).first()
                QuizResponse.objects.update_or_create(
                    attempt=attempt, question=question,
                    defaults={"selected_answer": correct_answer, "is_correct": True, "points_earned": question.points},
                )
        self.stdout.write(f"Seeded {quiz_count} Quiz, {question_count} QuizQuestion, {answer_count} QuizAnswer rows + 2 attempts.")

        # ── Exams: FSE101's already happened (graded response), DSM101's is
        #    upcoming (published, no response yet). ────────────────────────────
        def _mcq_options(correct_text, distractors):
            opts = [{"id": f"opt-{i}", "text": t, "is_correct": t == correct_text}
                    for i, t in enumerate([correct_text, *distractors])]
            return opts

        exam_defs = [
            ("FSE101", timezone.now() - timezone.timedelta(days=10), True),
            ("DSM101", timezone.now() + timezone.timedelta(days=10), False),
        ]
        exam_count = eq_count = 0
        for code, start, already_happened in exam_defs:
            lms = lms_courses[code]
            start = start.replace(hour=10, minute=0, second=0, microsecond=0)
            end = start + timezone.timedelta(minutes=90)
            exam, _ = Exam.objects.update_or_create(
                course=lms, title=f"{lms.title} — End of Course Exam",
                defaults={
                    "exam_type": Exam.END_OF_SEMESTER,
                    "instructor": instructor,
                    "start_datetime": start,
                    "end_datetime": end,
                    "total_marks": Decimal("20.00"),
                    "pass_mark": Decimal("12.00"),
                    "status": Exam.PUBLISHED,
                    "submitted_by": instructor,
                    "submitted_at": start - timezone.timedelta(days=5),
                    "approved_by": admin,
                    "approved_at": start - timezone.timedelta(days=4),
                    "published_by": admin,
                    "published_at": start - timezone.timedelta(days=3),
                    "created_by": instructor,
                    "instructions": "Answer all questions. You have 90 minutes.",
                },
            )
            exam_count += 1

            questions = []
            q1, _ = ExamQuestion.objects.update_or_create(
                exam=exam, question_text=f"What is the primary focus of {lms.title}?",
                defaults={"question_type": ExamQuestion.MCQ, "marks": Decimal("5.00"),
                          "options": _mcq_options(lms.title.split(":")[0], ["Sales & Marketing", "Facilities Management", "Event Planning"])},
            )
            q2, _ = ExamQuestion.objects.update_or_create(
                exam=exam, question_text="Best practices matter even under a deadline.",
                defaults={"question_type": ExamQuestion.TRUE_FALSE, "marks": Decimal("5.00"),
                          "options": [{"id": "t", "text": "True", "is_correct": True}, {"id": "f", "text": "False", "is_correct": False}]},
            )
            q3, _ = ExamQuestion.objects.update_or_create(
                exam=exam, question_text=f"Name one core skill taught in {lms.title}.",
                defaults={"question_type": ExamQuestion.SHORT_ANSWER, "marks": Decimal("5.00")},
            )
            q4, _ = ExamQuestion.objects.update_or_create(
                exam=exam, question_text=f"Describe a real scenario where you'd apply what {lms.title} teaches.",
                defaults={"question_type": ExamQuestion.ESSAY, "marks": Decimal("5.00")},
            )
            questions = [q1, q2, q3, q4]
            eq_count += len(questions)

            for i, log_status in enumerate(["submitted", "approved", "published"]):
                ExamStatusLog.objects.get_or_create(
                    exam=exam, to_status=log_status,
                    defaults={
                        "from_status": ["draft", "submitted", "approved"][i],
                        "changed_by": admin if log_status != "submitted" else instructor,
                        "note": f"Exam {log_status}.",
                    },
                )

            if already_happened:
                correct_opt = next(o["id"] for o in q1.options if o["is_correct"])
                response, _ = StudentExamResponse.objects.update_or_create(
                    exam=exam, student=student_user,
                    defaults={
                        "assigned_question_ids": [q.id for q in questions],
                        "answers": {str(q1.id): correct_opt, str(q2.id): "t", str(q3.id): "Building real projects"},
                        "question_scores": {
                            str(q1.id): {"marks_awarded": 5, "max_marks": 5, "is_correct": True},
                            str(q2.id): {"marks_awarded": 5, "max_marks": 5, "is_correct": True},
                            str(q3.id): {"marks_awarded": 4, "max_marks": 5, "is_correct": True},
                            str(q4.id): {"marks_awarded": 4, "max_marks": 5, "is_correct": None},
                        },
                        "total_score": Decimal("18.00"),
                        "score_percentage": Decimal("90.00"),
                        "passed": True,
                        "status": StudentExamResponse.GRADED,
                        "instructions_opened_at": start,
                        "exam_started_at": start,
                        "submitted_at": end,
                        "graded_by": instructor,
                        "graded_at": end + timezone.timedelta(days=1),
                        "pending_manual_count": 0,
                    },
                )
        self.stdout.write(f"Seeded {exam_count} Exam and {eq_count} ExamQuestion rows.")

        # ── Certificate for the completed FSE101 enrollment ─────────────────────
        Certificate.objects.update_or_create(
            student=student_user, course=lms_courses["FSE101"],
            defaults={
                "certificate_type": "lms_course",
                "completion_date": timezone.now().date(),
                "grade": "A",
                "payment_status": "paid",
            },
        )
        self.stdout.write("Seeded 1 Certificate row.")

        # ── Badges ────────────────────────────────────────────────────────────
        badge_data = [
            ("First Login", "Signed in to the platform for the first time.", "log-in"),
            ("First Course Registered", "Registered for your first course.", "book-open"),
            ("First Lesson Completed", "Completed your first lesson.", "check-circle"),
            ("Quiz Master", "Scored 100% on a knowledge check.", "award"),
            ("Course Completed", "Completed an entire course.", "trophy"),
            ("Certificate Earned", "Earned your first certificate.", "medal"),
        ]
        badges = {}
        for name, description, icon in badge_data:
            obj, _ = Badge.objects.update_or_create(name=name, defaults={"description": description, "icon": icon, "criteria": description, "is_active": True})
            badges[name] = obj
        self.stdout.write(f"Seeded {len(badge_data)} Badge rows.")

        earned = ["First Login", "First Course Registered", "First Lesson Completed", "Quiz Master", "Course Completed", "Certificate Earned"]
        for name in earned:
            StudentBadge.objects.update_or_create(
                student=student_user, badge=badges[name], defaults={"awarded_by": instructor},
            )
        self.stdout.write(f"Seeded {len(earned)} StudentBadge rows.")

        # ── Announcements ────────────────────────────────────────────────────
        announcement_data = [
            ("Welcome to the New Term!", "system", None, None, "Applications are open for the next intake — refer a friend and earn a badge."),
            ("Platform Maintenance This Weekend", "system", None, None, "We'll be performing scheduled maintenance Saturday night. Expect brief downtime."),
            ("New Lessons Added", "course", "FSE101", None, "We've added new lessons and exercises to this course — check them out."),
            ("Assignment Deadline Reminder", "course", "DSM101", None, "Don't forget: your practical assignment is due in two weeks."),
            ("New Cohort Starting Soon", "course", "CSA101", None, "A new cohort for this course starts next month — invite a colleague."),
            ("Web Development Resources Updated", "category", None, "Web Development", "We've refreshed the recommended reading list for this track."),
            ("Cybersecurity Lab Access", "category", None, "Cybersecurity", "New lab environments are now available for hands-on practice."),
            ("Data Science Office Hours", "category", None, "Data Science", "Join our weekly office hours for extra help with your data science projects."),
        ]
        announcement_count = 0
        for title, ann_type, course_code, category_name, content in announcement_data:
            Announcement.objects.update_or_create(
                title=title,
                defaults={
                    "content": content,
                    "announcement_type": ann_type,
                    "course": lms_courses.get(course_code) if course_code else None,
                    "category": categories.get(category_name) if category_name else None,
                    "created_by": instructor,
                    "is_active": True,
                },
            )
            announcement_count += 1
        self.stdout.write(f"Seeded {announcement_count} Announcement rows.")

        # ── Audit log ─────────────────────────────────────────────────────────
        audit_data = [
            (admin, "login", "User", "Admin logged in."),
            (admin, "create", "Program", "Created a new program."),
            (instructor, "login", "User", "Instructor logged in."),
            (instructor, "course_access", "LMSCourse", "Instructor accessed course management."),
            (student_user, "login", "User", "Student logged in."),
            (student_user, "registration", "CourseRegistration", "Student registered for a course."),
            (student_user, "assignment_submit", "AssignmentSubmission", "Student submitted an assignment."),
            (student_user, "exam_finish", "StudentExamResponse", "Student completed an exam."),
        ]
        for user, action, model_name, description in audit_data:
            AuditLog.objects.get_or_create(user=user, action=action, model_name=model_name, description=description)
        self.stdout.write(f"Seeded {len(audit_data)} AuditLog rows.")

    # ── Financial: fees, payments, invoices, transactions, payroll, subs ───────
    def _seed_financials(self, admin, instructor, support, finance, student_user, programs, lms_courses):
        gateways_data = [
            ("Stripe", "stripe", "pk_test_abraytech_placeholder"),
            ("PayPal", "paypal", "paypal_client_id_placeholder"),
        ]
        gateways = {}
        for name, gtype, api_key in gateways_data:
            obj, _ = PaymentGateway.objects.update_or_create(
                name=name, defaults={"gateway_type": gtype, "api_key": api_key, "is_active": False, "is_test_mode": True},
            )
            gateways[name] = obj
        self.stdout.write(f"Seeded {len(gateways_data)} PaymentGateway rows.")

        today = timezone.now().date()
        required_payments = []
        for code, program in programs.items():
            fee, _ = AllRequiredPayments.objects.update_or_create(
                program=program, purpose="Tuition Installment",
                defaults={"who_to_pay": "student", "amount": program.tuition_fee / 2, "due_date": today + timezone.timedelta(days=30)},
            )
            required_payments.append(fee)
            fee2, _ = AllRequiredPayments.objects.update_or_create(
                program=program, purpose="Certificate Fee",
                defaults={"who_to_pay": "student", "amount": Decimal("50.00"), "due_date": today + timezone.timedelta(days=180)},
            )
            required_payments.append(fee2)
        self.stdout.write(f"Seeded {len(required_payments)} AllRequiredPayments rows.")

        home_fee = AllRequiredPayments.objects.get(program__code="FSE", purpose="Tuition Installment")
        FeePayment.objects.update_or_create(
            fee=home_fee, user=student_user,
            defaults={"amount": home_fee.amount, "status": "success", "payment_method": "card", "card_last4": "4242", "card_brand": "Visa"},
        )
        self.stdout.write("Seeded 1 FeePayment row.")

        student_app = CourseApplication.objects.filter(user=student_user).first()
        if student_app:
            ApplicationPayment.objects.update_or_create(
                application=student_app,
                defaults={
                    "amount": student_app.application_fee, "status": "success",
                    "payment_method": "card", "card_last4": "4242", "card_brand": "Visa",
                },
            )
            self.stdout.write("Seeded 1 ApplicationPayment row.")

        invoice_data = [
            ("Tuition Installment 1", Decimal("600.00"), "paid"),
            ("Tuition Installment 2", Decimal("600.00"), "sent"),
            ("Certificate Fee", Decimal("50.00"), "paid"),
        ]
        for purpose, subtotal, status in invoice_data:
            Invoice.objects.update_or_create(
                student=student_user, course=lms_courses["FSE101"], notes=purpose,
                defaults={
                    "subtotal": subtotal, "tax_rate": Decimal("0.00"), "discount_amount": Decimal("0.00"),
                    "due_date": today + timezone.timedelta(days=30), "status": status,
                },
            )
        self.stdout.write(f"Seeded {len(invoice_data)} Invoice rows.")

        transaction_data = [
            ("enrollment", Decimal("1200.00"), "completed", "FSE101"),
            ("enrollment", Decimal("1900.00"), "completed", "DSM101"),
            ("subscription", Decimal("29.00"), "completed", None),
            ("refund", Decimal("50.00"), "refunded", None),
        ]
        for ttype, amount, status, course_code in transaction_data:
            Transaction.objects.get_or_create(
                user=student_user, transaction_type=ttype, amount=amount,
                defaults={"status": status, "gateway": gateways["Stripe"], "course": lms_courses.get(course_code) if course_code else None},
            )
        self.stdout.write(f"Seeded {len(transaction_data)} Transaction rows.")

        plans_data = [
            ("Basic", Decimal("9.00"), "monthly", ["Access to free courses", "Community forum access"]),
            ("Pro", Decimal("29.00"), "monthly", ["All Basic features", "Access to all paid courses", "Certificates"]),
            ("Enterprise", Decimal("99.00"), "monthly", ["All Pro features", "Team seats", "Priority support"]),
        ]
        plans = {}
        for order, (name, price, cycle, features) in enumerate(plans_data, start=1):
            obj, _ = SubscriptionPlan.objects.update_or_create(
                name=name, defaults={
                    "description": f"The {name} plan for Abraytech learners.",
                    "features": features, "price": price, "billing_cycle": cycle,
                    "is_popular": name == "Pro", "display_order": order,
                },
            )
            plans[name] = obj
        self.stdout.write(f"Seeded {len(plans_data)} SubscriptionPlan rows.")

        Subscription.objects.update_or_create(
            user=student_user, plan=plans["Pro"],
            defaults={"status": "active", "end_date": today + timezone.timedelta(days=335)},
        )
        self.stdout.write("Seeded 1 Subscription row.")

        staff_members = [instructor, admin, support, finance]
        this_month = timezone.now()
        payroll_count = 0
        for months_ago in (1, 0):
            period = (this_month.replace(day=1) - timezone.timedelta(days=1)) if months_ago == 1 else this_month
            for staff in staff_members:
                base = Decimal("2500.00") if staff.profile.role == "admin" else Decimal("1800.00")
                StaffPayroll.objects.update_or_create(
                    staff=staff, month=period.month, year=period.year,
                    defaults={
                        "base_salary": base, "allowances": Decimal("200.00"),
                        "tax_deduction": base * Decimal("0.10"),
                        "payment_status": "paid" if months_ago == 1 else "pending",
                        "payment_method": "bank_transfer",
                        "bank_name": "GTBank", "account_number": "0123456789",
                        "created_by": admin,
                    },
                )
                payroll_count += 1
        self.stdout.write(f"Seeded {payroll_count} StaffPayroll rows.")

    # ── Community: messages, notifications, discussions, study groups,
    #    reviews, broadcasts, contact messages, support tickets ────────────────
    def _seed_community(self, admin, instructor, support, student_user, lms_courses):
        message_data = [
            (student_user, instructor, "Question about the FSE101 assignment", "Hi Tunde, quick question about the practical assignment — is a README required?"),
            (instructor, student_user, "Re: Question about the FSE101 assignment", "Yes, please include a short README with setup instructions. Good work so far!"),
            (student_user, support, "Trouble accessing my certificate", "Hi, I can't find the download link for my FSE101 certificate — can you help?"),
            (support, student_user, "Re: Trouble accessing my certificate", "Hi Obi, it's under My Courses > Certificates. Let us know if that doesn't work."),
            (admin, student_user, "Welcome to Abraytech!", "Welcome aboard — let us know if you have any questions as you get started."),
            (student_user, admin, "Thank you!", "Thanks for the warm welcome — excited to get started."),
        ]
        for sender, recipient, subject, body in message_data:
            Message.objects.get_or_create(sender=sender, recipient=recipient, subject=subject, defaults={"body": body})
        self.stdout.write(f"Seeded {len(message_data)} Message rows.")

        notification_data = [
            ("enrollment", "Course Registered", "You registered for Web Fundamentals: HTML, CSS & JavaScript."),
            ("enrollment", "Course Registered", "You registered for Python for Data Science."),
            ("assignment", "Assignment Graded", "Your Web Fundamentals assignment was graded: 92/100."),
            ("grade", "New Grade Posted", "A new grade was posted for Web Fundamentals: HTML, CSS & JavaScript."),
            ("announcement", "New Announcement", "New Lessons Added to Web Fundamentals: HTML, CSS & JavaScript."),
            ("message", "New Message", "You have a new message from Tunde Bakare."),
            ("certificate", "Certificate Earned", "Congratulations! You earned a certificate for Web Fundamentals: HTML, CSS & JavaScript."),
            ("system", "Welcome to Abraytech", "Your account is ready — start exploring the course catalog."),
            ("account", "Email Verified", "Your email address has been verified."),
            ("quiz", "Quiz Completed", "You scored 100% on the Web Fundamentals knowledge check."),
        ]
        for ntype, title, message in notification_data:
            Notification.objects.get_or_create(user=student_user, notification_type=ntype, title=title, defaults={"message": message})
        self.stdout.write(f"Seeded {len(notification_data)} Notification rows.")

        discussion_data = [
            ("FSE101", "Best resources for learning Flexbox?", student_user, "Does anyone have extra resources for practicing CSS Flexbox layouts?"),
            ("BEP101", "Virtual environments vs. Poetry?", student_user, "Curious what everyone prefers for managing Python dependencies."),
            ("CSA101", "Wireshark capture filters", instructor, "Sharing a cheat sheet of useful Wireshark capture filters for the networking lab."),
            ("DSM101", "pandas groupby tips", student_user, "What are your favorite pandas groupby tricks for exploratory analysis?"),
            ("CDE101", "IAM policy least privilege", instructor, "A quick note on structuring least-privilege IAM policies on AWS."),
        ]
        discussion_count = reply_count = 0
        for course_code, title, author, content in discussion_data:
            lms = lms_courses[course_code]
            discussion, _ = Discussion.objects.update_or_create(
                course=lms, title=title, defaults={"content": content, "author": author},
            )
            discussion_count += 1
            replier = instructor if author != instructor else student_user
            DiscussionReply.objects.get_or_create(
                discussion=discussion, author=replier,
                defaults={"content": "Good question — here's what's worked well for me."},
            )
            reply_count += 1
        self.stdout.write(f"Seeded {discussion_count} Discussion and {reply_count} DiscussionReply rows.")

        review_data = [
            ("FSE101", 5, "Clear, practical, and genuinely helped me build real projects."),
            ("DSM101", 4, "Great intro to the data science toolkit — would love more advanced content."),
        ]
        for course_code, rating, text in review_data:
            Review.objects.update_or_create(
                course=lms_courses[course_code], student=student_user,
                defaults={"rating": rating, "review_text": text},
            )
        self.stdout.write(f"Seeded {len(review_data)} Review rows.")

        groups_data = [
            ("FSE101", "FSE101 Study Group"),
            ("DSM101", "Data Science Study Circle"),
            ("CSA101", "Cybersecurity Study Group"),
        ]
        group_count = member_count = group_message_count = 0
        for course_code, name in groups_data:
            group, _ = StudyGroup.objects.update_or_create(
                name=name, defaults={"course": lms_courses[course_code], "created_by": instructor},
            )
            group_count += 1
            StudyGroupMember.objects.get_or_create(study_group=group, user=instructor, defaults={"role": "moderator"})
            StudyGroupMember.objects.get_or_create(study_group=group, user=student_user, defaults={"role": "member"})
            member_count += 2
            StudyGroupMessage.objects.get_or_create(
                study_group=group, author=student_user,
                defaults={"content": "Looking forward to studying together in this group!"},
            )
            group_message_count += 1
        self.stdout.write(f"Seeded {group_count} StudyGroup, {member_count} StudyGroupMember, {group_message_count} StudyGroupMessage rows.")

        broadcast_data = [
            ("New Programs Available for Next Intake", "all_users", "sent"),
            ("Reminder: Complete Your Profile", "role", "sent"),
            ("Upcoming Platform Downtime", "all_users", "draft"),
        ]
        for subject, filter_type, status in broadcast_data:
            BroadcastMessage.objects.update_or_create(
                subject=subject,
                defaults={
                    "message": f"{subject} — details inside.", "filter_type": filter_type,
                    "filter_values": {}, "status": status, "created_by": admin,
                    "sent_at": timezone.now() if status == "sent" else None,
                },
            )
        self.stdout.write(f"Seeded {len(broadcast_data)} BroadcastMessage rows.")

        contact_data = [
            ("Tobi Adebayo", "tobi.adebayo@example.com", "admissions", "I'd like to know more about the Full-Stack Software Engineering program."),
            ("Linda Chukwu", "linda.chukwu@example.com", "programs", "Do you offer a part-time option for the Data Science track?"),
            ("Femi Alabi", "femi.alabi@example.com", "financial", "Is financial aid available for the Cybersecurity Analyst Program?"),
            ("Grace Eze", "grace.eze@example.com", "support", "I'm having trouble uploading my application documents."),
            ("Ben Carter", "ben.carter@example.com", "other", "Interested in a corporate training partnership — who should I speak to?"),
            ("Chioma Nnamdi", "chioma.nnamdi@example.com", "campus", "Can I schedule a visit to the Lagos office?"),
        ]
        for name, email, subject, message in contact_data:
            ContactMessage.objects.get_or_create(email=email, subject=subject, defaults={"name": name, "message": message})
        self.stdout.write(f"Seeded {len(contact_data)} ContactMessage rows.")

        ticket_data = [
            ("technical", "Video lessons won't load", "The video for Lesson 2 keeps buffering and never plays.", "high"),
            ("account", "Can't reset my password", "The password reset email never arrives.", "normal"),
            ("course", "Missing lesson content", "Lesson 3 in Python for Data Science appears to be empty.", "normal"),
            ("payment", "Duplicate charge on my card", "I think I was charged twice for my tuition installment.", "urgent"),
            ("other", "How do I download my transcript?", "Just wondering where to find my academic records.", "low"),
        ]
        ticket_count = reply_count2 = 0
        for category, subject, description, priority in ticket_data:
            ticket, _ = SupportTicket.objects.update_or_create(
                user=student_user, subject=subject,
                defaults={"category": category, "description": description, "priority": priority, "assigned_to": support, "status": "resolved"},
            )
            ticket_count += 1
            TicketReply.objects.get_or_create(
                ticket=ticket, author=support,
                defaults={"message": "Thanks for reaching out — we've looked into this and resolved it. Let us know if it happens again."},
            )
            reply_count2 += 1
        self.stdout.write(f"Seeded {ticket_count} SupportTicket and {reply_count2} TicketReply rows.")

    # ── Misc: course grades, application documents, staff permission defaults ──
    def _seed_misc(self, student_user, courses):
        CourseGrade.objects.update_or_create(
            student=student_user, course=courses["FSE101"],
            defaults={"score": Decimal("92.00"), "grade": "A", "credit_units": 3, "is_passed": True, "result_status": "released"},
        )
        self.stdout.write("Seeded 1 CourseGrade row.")

        student_app = CourseApplication.objects.filter(user=student_user).first()
        if student_app:
            doc_data = [
                ("transcript", "transcript.pdf", b"Seed placeholder transcript document."),
                ("id_document", "national_id.pdf", b"Seed placeholder ID document."),
                ("cv", "resume.pdf", b"Seed placeholder resume/CV document."),
            ]
            doc_count = 0
            for file_type, filename, content in doc_data:
                if not ApplicationDocument.objects.filter(application=student_app, file_type=file_type).exists():
                    doc = ApplicationDocument(
                        application=student_app, file_type=file_type,
                        original_filename=filename, file_size=len(content),
                    )
                    doc.file.save(filename, ContentFile(content), save=True)
                doc_count += 1
            self.stdout.write(f"Seeded {doc_count} ApplicationDocument rows.")

        for role in ("admin", "support", "finance", "instructor"):
            StaffPermissionsMatrix.seed_defaults_for_role(role)
        self.stdout.write(f"Seeded StaffPermissionsMatrix defaults for admin/support/finance/instructor "
                           f"({StaffPermissionsMatrix.objects.count()} rows total).")

        library_data = [
            ("Books", "Software Engineering", "Clean Code", "Robert C. Martin", "https://example.com/library/clean-code"),
            ("Books", "Software Engineering", "Designing Data-Intensive Applications", "Martin Kleppmann", "https://example.com/library/ddia"),
            ("Books", "Cybersecurity", "The Web Application Hacker's Handbook", "Dafydd Stuttard", "https://example.com/library/web-hackers-handbook"),
            ("Books", "AI & Data", "Python for Data Analysis", "Wes McKinney", "https://example.com/library/python-data-analysis"),
            ("Books", "Cloud & DevOps", "The Phoenix Project", "Gene Kim", "https://example.com/library/phoenix-project"),
            ("Periodicals", "Abraytech Tech Digest", "Abraytech Tech Digest — Issue 1", "Abraytech Editorial Team", "https://example.com/library/digest-1"),
            ("Periodicals", "Abraytech Tech Digest", "Abraytech Tech Digest — Issue 2", "Abraytech Editorial Team", "https://example.com/library/digest-2"),
            ("References", "Style Guides", "Abraytech API Style Guide", "Abraytech Engineering", "https://example.com/library/api-style-guide"),
            ("References", "Cheat Sheets", "Linux Command Line Cheat Sheet", "Abraytech Training Team", "https://example.com/library/linux-cheatsheet"),
            ("Other", "Career Resources", "Technical Interview Prep Pack", "Abraytech Careers Team", "https://example.com/library/interview-prep"),
        ]
        for category, subcategory, title, author, url in library_data:
            LibraryItem.objects.update_or_create(
                title=title, defaults={"category": category, "subcategory": subcategory, "author": author, "external_url": url, "access": "members"},
            )
        self.stdout.write(f"Seeded {len(library_data)} LibraryItem rows.")

    # ── Faculties ────────────────────────────────────────────────────────
    def _seed_faculties(self):
        data = [
            dict(
                name="Software Engineering", code="SWE",
                tagline="Build and ship production software.",
                description=(
                    "Hands-on training in modern web and software engineering — "
                    "from first line of code to deployed, production-grade applications."
                ),
            ),
            dict(
                name="Cybersecurity", code="CSEC",
                tagline="Defend the systems the world runs on.",
                description=(
                    "Practical security training covering networking, security operations, "
                    "ethical hacking and governance/risk/compliance."
                ),
            ),
            dict(
                name="AI & Data", code="AID",
                tagline="Turn data into decisions.",
                description=(
                    "Data science and machine learning training focused on real analysis, "
                    "modeling and storytelling with data."
                ),
            ),
            dict(
                name="Cloud & DevOps", code="CDO",
                tagline="Run infrastructure at scale.",
                description=(
                    "Cloud, containers and infrastructure-as-code training for engineers who "
                    "want to own the systems software runs on."
                ),
            ),
        ]
        faculties = {}
        for row in data:
            obj, created = Faculty.objects.update_or_create(
                code=row["code"],
                defaults={
                    "name": row["name"],
                    "tagline": row["tagline"],
                    "description": row["description"],
                    "is_active": True,
                },
            )
            faculties[row["code"]] = obj
            self.stdout.write(f"{'Created' if created else 'Updated'} faculty: {obj.name}")
        return faculties

    # ── Departments ──────────────────────────────────────────────────────
    def _seed_departments(self, faculties):
        data = [
            dict(faculty="SWE", name="Software Development", code="SWD"),
            dict(faculty="CSEC", name="Cybersecurity Operations", code="CSO"),
            dict(faculty="AID", name="Data Science & AI", code="DSA"),
            dict(faculty="CDO", name="Cloud & DevOps Engineering", code="CDE"),
        ]
        departments = {}
        for row in data:
            obj, created = Department.objects.update_or_create(
                faculty=faculties[row["faculty"]], code=row["code"],
                defaults={"name": row["name"], "is_active": True},
            )
            departments[row["code"]] = obj
            self.stdout.write(f"{'Created' if created else 'Updated'} department: {obj.name}")
        return departments

    # ── Programs ─────────────────────────────────────────────────────────
    def _seed_programs(self, departments):
        data = [
            dict(
                dept="SWD", code="FSE", name="Full-Stack Software Engineering",
                degree_level="certificate", duration_years=Decimal("0.5"),
                credits_required=12, application_fee=Decimal("50.00"), tuition_fee=Decimal("1200.00"),
                available_study_modes=["Full Time", "Online"],
                tagline="Ship real full-stack products in six months.",
                overview="A job-ready track covering frontend, backend and deployment.",
                description=(
                    "Learn to design, build and ship full-stack web applications — from "
                    "responsive frontends to REST APIs to production deployment."
                ),
                entry_requirements=[
                    "Basic computer literacy", "Problem-solving aptitude",
                    "No prior coding experience required",
                ],
                core_courses=[
                    "Web Fundamentals (HTML/CSS/JS)", "JavaScript & React",
                    "Backend APIs with Node.js", "Git, Testing & Deployment",
                ],
                specialization_tracks=["Frontend Engineering", "Backend Engineering", "Full-Stack Product Development"],
                learning_outcomes=[
                    "Build and deploy full-stack web applications",
                    "Work confidently with modern JavaScript frameworks",
                    "Design and consume REST APIs",
                    "Collaborate using Git and agile workflows",
                ],
                career_paths=["Frontend Developer", "Backend Developer", "Full-Stack Software Engineer"],
            ),
            dict(
                dept="SWD", code="BEP", name="Backend Engineering with Python & Django",
                degree_level="diploma", duration_years=Decimal("1.0"),
                credits_required=12, application_fee=Decimal("50.00"), tuition_fee=Decimal("1800.00"),
                available_study_modes=["Full Time", "Part Time", "Online"],
                tagline="Master backend systems with Python and Django.",
                overview="A deeper backend track for engineers who want to specialize in server-side systems.",
                description=(
                    "Go deep on Python, relational databases and the Django framework to build "
                    "reliable, secure backend systems and APIs."
                ),
                entry_requirements=["Basic programming familiarity", "Comfort with the command line"],
                core_courses=[
                    "Python Programming Foundations", "Django Web Framework",
                    "Databases & SQL", "REST API Design",
                ],
                specialization_tracks=["API Engineering", "Systems Architecture"],
                learning_outcomes=[
                    "Design normalized relational database schemas",
                    "Build production Django applications",
                    "Design and document REST APIs",
                ],
                career_paths=["Backend Engineer", "Python Developer", "API Engineer"],
            ),
            dict(
                dept="CSO", code="CSA", name="Cybersecurity Analyst Program",
                degree_level="diploma", duration_years=Decimal("1.0"),
                credits_required=12, application_fee=Decimal("60.00"), tuition_fee=Decimal("2000.00"),
                available_study_modes=["Full Time", "Online"],
                tagline="Become a job-ready security analyst.",
                overview="Practical security operations training from networking basics to ethical hacking.",
                description=(
                    "Learn to monitor, defend and test the security of networks and systems — "
                    "covering SIEM operations, penetration testing and compliance."
                ),
                entry_requirements=["Basic networking familiarity is a plus, not required"],
                core_courses=[
                    "Networking Fundamentals", "Security Operations & SIEM",
                    "Ethical Hacking & Pentesting", "Governance, Risk & Compliance",
                ],
                specialization_tracks=["SOC Analyst", "Penetration Testing"],
                learning_outcomes=[
                    "Analyze network traffic and identify threats",
                    "Operate SIEM tooling in a security operations center",
                    "Perform basic penetration tests under an ethical framework",
                ],
                career_paths=["SOC Analyst", "Penetration Tester", "Security Consultant"],
            ),
            dict(
                dept="DSA", code="DSM", name="Data Science & Machine Learning",
                degree_level="diploma", duration_years=Decimal("1.0"),
                credits_required=12, application_fee=Decimal("55.00"), tuition_fee=Decimal("1900.00"),
                available_study_modes=["Full Time", "Online"],
                tagline="Turn raw data into real decisions.",
                overview="A practical data science track from Python fundamentals to machine learning.",
                description=(
                    "Learn to wrangle, analyze, visualize and model data using Python, pandas "
                    "and core machine learning techniques."
                ),
                entry_requirements=["Comfort with basic math/statistics is helpful, not required"],
                core_courses=[
                    "Python for Data Science", "Statistics & Data Analysis",
                    "Machine Learning Fundamentals", "Data Visualization & Storytelling",
                ],
                specialization_tracks=["Data Analytics", "Machine Learning"],
                learning_outcomes=[
                    "Clean and analyze real-world datasets with pandas",
                    "Build and evaluate machine learning models",
                    "Communicate findings through clear data visualization",
                ],
                career_paths=["Data Analyst", "Data Scientist", "Machine Learning Engineer"],
            ),
            dict(
                dept="CDE", code="CDE", name="Cloud & DevOps Engineering",
                degree_level="certificate", duration_years=Decimal("0.5"),
                credits_required=12, application_fee=Decimal("50.00"), tuition_fee=Decimal("1500.00"),
                available_study_modes=["Full Time", "Online"],
                tagline="Own the infrastructure software runs on.",
                overview="A hands-on cloud/DevOps track covering AWS, containers and infrastructure as code.",
                description=(
                    "Learn to provision, automate and monitor cloud infrastructure using AWS, "
                    "Docker, Kubernetes and Terraform."
                ),
                entry_requirements=["Basic Linux/command-line familiarity is a plus"],
                core_courses=[
                    "Linux & Cloud Fundamentals (AWS)", "CI/CD & Containers",
                    "Infrastructure as Code (Terraform)", "Site Reliability & Monitoring",
                ],
                specialization_tracks=["Cloud Infrastructure", "Site Reliability Engineering"],
                learning_outcomes=[
                    "Provision and manage cloud infrastructure on AWS",
                    "Build CI/CD pipelines with containerized deployments",
                    "Write infrastructure as code with Terraform",
                ],
                career_paths=["Cloud Engineer", "DevOps Engineer", "Site Reliability Engineer"],
            ),
        ]
        programs = {}
        for row in data:
            dept = departments[row.pop("dept")]
            code = row.pop("code")
            obj, created = Program.objects.update_or_create(
                department=dept, code=code,
                defaults={**row, "is_active": True},
            )
            programs[code] = obj
            self.stdout.write(f"{'Created' if created else 'Updated'} program: {obj.name}")
        return programs

    # ── Courses ──────────────────────────────────────────────────────────
    def _seed_courses(self, programs):
        # (program_code, course_code, name, course_type)
        data = [
            ("FSE", "FSE101", "Web Fundamentals: HTML, CSS & JavaScript", "core"),
            ("FSE", "FSE102", "JavaScript & React", "core"),
            ("FSE", "FSE103", "Backend APIs with Node.js", "core"),
            ("FSE", "FSE104", "Git, Testing & Deployment", "elective"),

            ("BEP", "BEP101", "Python Programming Foundations", "core"),
            ("BEP", "BEP102", "Django Web Framework", "core"),
            ("BEP", "BEP103", "Databases & SQL", "core"),
            ("BEP", "BEP104", "REST API Design", "elective"),

            ("CSA", "CSA101", "Networking Fundamentals for Security", "core"),
            ("CSA", "CSA102", "Security Operations & SIEM", "core"),
            ("CSA", "CSA103", "Ethical Hacking & Pentesting", "core"),
            ("CSA", "CSA104", "Governance, Risk & Compliance", "elective"),

            ("DSM", "DSM101", "Python for Data Science", "core"),
            ("DSM", "DSM102", "Statistics & Data Analysis", "core"),
            ("DSM", "DSM103", "Machine Learning Fundamentals", "core"),
            ("DSM", "DSM104", "Data Visualization & Storytelling", "elective"),

            ("CDE", "CDE101", "Linux & Cloud Fundamentals (AWS)", "core"),
            ("CDE", "CDE102", "CI/CD & Containers", "core"),
            ("CDE", "CDE103", "Infrastructure as Code (Terraform)", "core"),
            ("CDE", "CDE104", "Site Reliability & Monitoring", "elective"),
        ]
        courses = {}
        for prog_code, course_code, name, course_type in data:
            obj, created = Course.objects.update_or_create(
                program=programs[prog_code], code=course_code,
                defaults={
                    "name": name, "course_type": course_type,
                    "credit_units": 3, "is_active": True,
                },
            )
            courses[course_code] = obj
            self.stdout.write(f"{'Created' if created else 'Updated'} course: {obj.code} — {obj.name}")
        return courses

    # ── Users (one per role) + flagship LMS courses + demo enrollment ──────
    def _seed_users(self, programs, courses):
        instructor = self._seed_user(
            username="tunde.bakare", email="tunde.bakare@abraytech.com",
            first_name="Tunde", last_name="Bakare", role="instructor",
        )
        admin = self._seed_user(
            username="chidinma.okafor", email="chidinma.okafor@abraytech.com",
            first_name="Chidinma", last_name="Okafor", role="admin",
            is_staff=True, is_superuser=True,
        )
        support = self._seed_user(
            username="ada.nwosu", email="ada.nwosu@abraytech.com",
            first_name="Ada", last_name="Nwosu", role="support",
        )
        finance = self._seed_user(
            username="emeka.udo", email="emeka.udo@abraytech.com",
            first_name="Emeka", last_name="Udo", role="finance",
        )
        student_user = self._seed_user(
            username="obikolade", email="obikolade@gmail.com",
            first_name="Obi", last_name="Kolade", role="student",
        )

        # ── Flagship LMS courses, one per program, taught by the seeded instructor ──
        lms_data = [
            (
                "FSE101", "Web Fundamentals: HTML, CSS & JavaScript",
                "Learn to build responsive, accessible web pages from scratch.",
                [
                    ("Course Overview & Setting Up Your Dev Environment", True),
                    ("HTML5 Semantics & Accessible Markup", False),
                    ("CSS Layout: Flexbox & Grid", False),
                    ("JavaScript Fundamentals: Variables, Functions & the DOM", False),
                ],
            ),
            (
                "BEP101", "Python Programming Foundations",
                "A hands-on introduction to Python for aspiring backend engineers.",
                [
                    ("Welcome to Python: Installing & Your First Script", True),
                    ("Data Types, Variables & Control Flow", False),
                    ("Functions, Modules & Error Handling", False),
                    ("Working with Files & the Python Standard Library", False),
                ],
            ),
            (
                "CSA101", "Networking Fundamentals for Security",
                "The networking foundation every security analyst needs.",
                [
                    ("Introduction to Networking & the OSI Model", True),
                    ("TCP/IP, DNS & Routing Essentials", False),
                    ("Firewalls, VPNs & Network Segmentation", False),
                    ("Packet Analysis with Wireshark", False),
                ],
            ),
            (
                "DSM101", "Python for Data Science",
                "Get hands-on with the core Python data science toolkit.",
                [
                    ("Setting Up Your Data Science Toolkit (Jupyter, NumPy, pandas)", True),
                    ("Data Wrangling with pandas", False),
                    ("Exploratory Data Analysis & Visualization", False),
                    ("Intro to Statistics for Data Science", False),
                ],
            ),
            (
                "CDE101", "Linux & Cloud Fundamentals (AWS)",
                "Provision and manage your first cloud infrastructure on AWS.",
                [
                    ("Linux Command Line Essentials", True),
                    ("AWS Core Services: EC2, S3 & IAM", False),
                    ("Provisioning Your First Cloud Environment", False),
                    ("Monitoring & Cost Management Basics", False),
                ],
            ),
        ]

        lms_courses = {}
        for course_code, title, short_desc, lessons in lms_data:
            academic_course = courses[course_code]
            lms, created = LMSCourse.objects.update_or_create(
                code=course_code,
                defaults={
                    "title": title,
                    "short_description": short_desc,
                    "description": short_desc,
                    "academic_course": academic_course,
                    "instructor": instructor,
                    "lecturer": instructor,
                    "is_published": True,
                },
            )
            lms_courses[course_code] = lms
            self.stdout.write(f"{'Created' if created else 'Updated'} LMS course: {lms.title}")

            for order, (lesson_title, is_preview) in enumerate(lessons, start=1):
                Lesson.objects.update_or_create(
                    course=lms, title=lesson_title,
                    defaults={
                        "lesson_type": "text",
                        "content": f"Lesson content for “{lesson_title}”.",
                        "is_preview": is_preview,
                        "is_active": True,
                        "display_order": order,
                    },
                )

        # ── Demo student: approved application, accepted admission, two
        #    registrations — one inside their own program, one in a totally
        #    different program, proving the flat catalog. ──────────────────
        home_program = programs["FSE"]
        application, _ = CourseApplication.objects.update_or_create(
            user=student_user, program=home_program,
            defaults={
                "first_name": student_user.first_name,
                "last_name": student_user.last_name,
                "email": student_user.email,
                "phone": "+2348012345678",
                "gender": "male",
                "nationality": "Nigerian",
                "address_line1": "14 Admiralty Way, Lekki Phase 1",
                "city": "Lagos",
                "state": "Lagos",
                "country": "Nigeria",
                "highest_qualification": "High School Diploma",
                "accept_privacy_policy": True,
                "accept_terms_conditions": True,
                "status": "approved",
                "payment_status": "success",
                "department_approved": True,
                "department_approved_at": timezone.now(),
            },
        )
        if not application.admission_accepted:
            application.accept_admission()
        if not application.admission_number:
            application.issue_admission_number()

        profile = student_user.profile
        profile.program = home_program
        profile.department = home_program.department
        profile.faculty = home_program.department.faculty
        profile.save(update_fields=["program", "department", "faculty"])

        for course_code in ("FSE101", "DSM101"):
            course = courses[course_code]
            reg, _ = CourseRegistration.objects.update_or_create(
                student=student_user, course=course,
                defaults={"status": "approved"},
            )
            lms = lms_courses[course_code]
            Enrollment.objects.update_or_create(
                student=student_user, course=lms,
                defaults={"enrolled_by": student_user, "status": "active"},
            )
        self.stdout.write(
            "Registered obikolade for FSE101 (own program) and DSM101 "
            "(a different program) to demonstrate the flat catalog."
        )

        return instructor, admin, support, finance, student_user, lms_courses

    def _seed_user(self, *, username, email, first_name, last_name, role, is_staff=False, is_superuser=False):
        user, created = User.objects.update_or_create(
            username=username,
            defaults={
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "is_active": True,
                "is_staff": is_staff,
                "is_superuser": is_superuser,
            },
        )
        user.set_password(SEED_PASSWORD)
        user.save()

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = role
        profile.email_verified = True
        profile.save(update_fields=["role", "email_verified"])

        self.stdout.write(f"{'Created' if created else 'Updated'} user: {username} ({role}) — {email}")
        return user
