"""
Seed the public marketing site with the real, approved copy from
"AbrayTech Website Content Development.docx": SiteConfig (homepage hero/
About/Why-us/process/newsletter/apply copy, mission/vision/values, footer
tagline, confirmed social links), the six Services-page service cards, the
Resources/Blog categories, and the 5 "Digital Solutions" products shown on
the Projects & Portfolio page.

Companion command: `seed_courses` seeds the backend
Faculty/Department/Program/Course data for the AbrayTech Academy training
programmes described in the same document; run both to fully apply the
document's content.

Deliberately NOT touched here (the source document has no confirmed data
for these, or explicitly says so (see the document's own caveats):
  - office_hours_*, address_usa/nigeria, phone_*, email_* on SiteConfig:
    the document explicitly says current placeholder hours/contact details
    "should be reviewed for accuracy before final publication."
  - Industry, JobListing, Testimonial, InstitutionPartner: the document
    only gives page *structure* guidance for these, not literal instances.
  - The Store page/categories: out of scope by request.

Idempotent: safe to re-run. Services/BlogCategories/Projects are matched by
their *old* placeholder title/name first (so a first run renames them in
place) and by their new title/name on subsequent runs (so re-running just
refreshes the copy instead of duplicating rows).
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.eduweb.models import SiteConfig, Service, BlogCategory, Project


class Command(BaseCommand):
    help = "Seed real AbrayTech public-site copy (SiteConfig, Services, Blog categories, Digital Solutions projects) from the Website Content Development document."

    @transaction.atomic
    def handle(self, *args, **options):
        self._seed_site_config()
        self._seed_homepage_content()
        self._seed_services()
        self._seed_blog_categories()
        self._seed_digital_solutions()
        self.stdout.write(self.style.SUCCESS("\nPublic content seed complete."))
        self.stdout.write(
            "Note: office hours, phone numbers, and addresses were left untouched. "
            "The source document flags these as unconfirmed and needing sign-off "
            "before publishing."
        )

    # ── SiteConfig: About page + footer + confirmed social links ────────────
    def _seed_site_config(self):
        site_config = SiteConfig.get()

        site_config.about_mission = (
            "To make innovative, secure, and practical technology solutions "
            "accessible to businesses and individuals, enabling them to improve "
            "performance, embrace digital opportunities, and achieve sustainable "
            "growth."
        )
        site_config.about_vision = (
            "To become a trusted technology partner recognized for practical "
            "innovation, secure digital solutions, professional development, and "
            "positive contributions to the digital economy."
        )
        site_config.about_values = [
            "Innovation: explore better ways to solve problems.",
            "Integrity: communicate honestly and act responsibly.",
            "Security: prioritize protection, privacy, and responsible technology.",
            "Collaboration: work with clients and learners to achieve shared goals.",
            "Continuous learning: improve our knowledge, skills, and services.",
        ]
        site_config.footer_tagline = (
            "AbrayTech is a technology solutions and education company helping "
            "businesses and individuals adopt digital tools, improve operational "
            "efficiency, strengthen cybersecurity, and develop the skills needed "
            "for the modern economy."
        )

        # Confirmed, verified handles from the document's own "Social links" list.
        site_config.facebook = "https://www.facebook.com/Abraytech"
        site_config.instagram = "https://www.instagram.com/abraytech"
        site_config.youtube = "https://www.youtube.com/@abraytech"
        site_config.tiktok = "https://www.tiktok.com/@abraytech"

        site_config.save(update_fields=[
            "about_mission", "about_vision", "about_values", "footer_tagline",
            "facebook", "instagram", "youtube", "tiktok",
        ])
        self.stdout.write("Updated SiteConfig: about mission/vision/values, footer tagline, confirmed social links.")

    # ── Homepage: hero, About heading, Why-us, process, newsletter, apply ───
    def _seed_homepage_content(self):
        site_config = SiteConfig.get()

        site_config.home_hero_heading = "Building Digital Solutions for a Smarter Future."
        site_config.home_hero_subheading = (
            "Empowering businesses, organizations, and individuals through "
            "innovative software solutions, cybersecurity, artificial "
            "intelligence, data solutions, and technology education."
        )
        site_config.home_hero_cta_primary_label = "Let's Talk"
        site_config.home_hero_cta_secondary_label = "Explore Our Services"
        site_config.home_hero_highlights = [
            "Security-first delivery",
            "Practical, scalable solutions",
            "Technology expertise and responsive support",
        ]

        site_config.home_about_heading = "Technology That Works for Your Ambition"

        site_config.home_why_us_heading = "More Than a Technology Vendor"
        site_config.home_why_us_items = [
            {
                "title": "End-to-end capabilities",
                "description": "Bring software, security, AI, data, and training together through one technology partner.",
            },
            {
                "title": "Security by design",
                "description": "Consider security architecture and testing throughout the development lifecycle.",
            },
            {
                "title": "Practical solutions",
                "description": "Develop systems with real business needs, usability, and maintainability in mind.",
            },
            {
                "title": "Responsive collaboration",
                "description": "Work closely with clients through discovery, design, delivery, and ongoing support.",
            },
        ]

        site_config.home_process_heading = "From Ideas to Impact"
        site_config.home_process_steps = [
            {"title": "Discover", "description": "Understand your goals, challenges, users, and requirements."},
            {"title": "Design", "description": "Plan the solution architecture, user experience, and delivery approach."},
            {"title": "Build & Secure", "description": "Develop iteratively with testing and security reviews."},
            {"title": "Launch & Support", "description": "Deploy the solution and provide continued support where required."},
        ]

        site_config.home_newsletter_heading = "Stay Ahead of the Curve"
        site_config.home_newsletter_subheading = (
            "Receive occasional insights, technology updates, training "
            "opportunities, and practical information on software, "
            "cybersecurity, AI, and digital transformation."
        )

        # "Your Learning Journey" from the document's Academy section. No
        # fixed review timeframe promised, per the document's own caution
        # against committing to an admissions turnaround that isn't real.
        site_config.home_apply_heading = "Your Learning Journey"
        site_config.home_apply_subheading = (
            "Whether you are starting your ICT journey or building on "
            "existing knowledge, explore a learning path that matches your goals."
        )
        site_config.home_apply_steps = [
            {"title": "Explore Programs", "description": "Explore available programs to find the training path that matches your goals."},
            {"title": "Submit Your Application", "description": "Submit your application with your background and goals."},
            {"title": "Complete Assessment", "description": "Complete any required assessment or interview for your chosen program."},
            {"title": "Begin Your Journey", "description": "Receive enrollment information and begin your learning journey."},
        ]

        site_config.save(update_fields=[
            "home_hero_heading", "home_hero_subheading", "home_hero_cta_primary_label",
            "home_hero_cta_secondary_label", "home_hero_highlights",
            "home_about_heading",
            "home_why_us_heading", "home_why_us_items",
            "home_process_heading", "home_process_steps",
            "home_newsletter_heading", "home_newsletter_subheading",
            "home_apply_heading", "home_apply_subheading", "home_apply_steps",
        ])
        self.stdout.write("Updated SiteConfig: homepage hero, Why-us, process, newsletter, and apply-steps copy.")

    # ── Services page: the 6 real service offerings ─────────────────────────
    def _seed_services(self):
        # (old placeholder title to match on a first run, new real title,
        #  summary, full description, icon)
        services_data = [
            (
                "Custom Software Development", "Custom Software Development",
                "Custom web, mobile, and business applications designed around "
                "your processes, users, and growth objectives.",
                "We design and develop business applications that support your "
                "operational processes, improve efficiency, and create better "
                "digital experiences.\n\n"
                "Services include:\n"
                "- AI, agentic AI automation\n"
                "- Web application development\n"
                "- Business management systems\n"
                "- Mobile application development\n"
                "- API development and integration\n"
                "- Application maintenance and enhancement\n"
                "- Software architecture and SDLC support",
                "code",
            ),
            (
                "Cybersecurity & Penetration Testing", "Cybersecurity Services",
                "Security-focused services that help organizations identify "
                "risks, protect digital assets, and improve their security "
                "posture.",
                "AbrayTech supports organizations in understanding and managing "
                "cybersecurity risks through practical, security-focused "
                "solutions.\n\n"
                "Services include:\n"
                "- Cybersecurity assessment, penetration testing, and advisory\n"
                "- Security awareness training\n"
                "- Secure application development\n"
                "- Cybersecurity policy and compliance support\n"
                "- Vulnerability and risk management guidance\n"
                "- Data protection, GDPR, and Cyber Essentials readiness support\n\n"
                "Security is considered throughout the solution lifecycle, from "
                "planning and development to deployment and ongoing improvement.",
                "shield",
            ),
            (
                "AI & Data Engineering", "AI & Machine Learning",
                "Intelligent solutions, analytics, and data-driven systems that "
                "support better decisions and operational improvements.",
                "Explore AI and machine learning solutions that support "
                "automation, insights, and improved decision-making.\n\n"
                "Services include:\n"
                "- AI-powered application features\n"
                "- Machine learning model development\n"
                "- Intelligent recommendations\n"
                "- Data-driven automation\n"
                "- AI research and prototyping\n"
                "- Integration of AI into business workflows\n"
                "- AI and machine learning research and development",
                "brain-circuit",
            ),
            (
                "Data Analytics & Business Intelligence", "Data Analytics & Business Intelligence",
                "Help your organization understand its data and use meaningful "
                "insights to improve operations and planning.",
                "Turn data into actionable insights.\n\n"
                "Services include:\n"
                "- Data analysis and reporting\n"
                "- Power BI dashboards\n"
                "- Business intelligence solutions\n"
                "- Data preparation and transformation\n"
                "- Predictive analytics\n"
                "- Reporting workflow improvement",
                "bar-chart-3",
            ),
            (
                "IT Consulting & Strategy", "IT Consulting & Digital Transformation",
                "Practical implementation strategies to help you plan, improve, "
                "and modernize your technology.",
                "We help businesses identify technology opportunities, evaluate "
                "their digital needs, and develop practical implementation "
                "strategies.\n\n"
                "Services include:\n"
                "- IT strategy and advisory\n"
                "- Digital transformation planning\n"
                "- Technology architecture\n"
                "- System integration\n"
                "- Process automation\n"
                "- Technology project guidance",
                "compass",
            ),
            (
                "Managed IT Support", "IT Support & Infrastructure",
                "Reliable technology support for the everyday needs of "
                "individuals and businesses.",
                "Support the everyday technology needs of individuals and "
                "businesses through practical IT assistance and infrastructure "
                "guidance.\n\n"
                "Services include:\n"
                "- IT support and troubleshooting\n"
                "- Network setup and advisory\n"
                "- Cloud and deployment guidance\n"
                "- Linux and server support\n"
                "- System maintenance\n"
                "- Business technology setup",
                "life-buoy",
            ),
        ]

        updated = 0
        for old_title, new_title, summary, description, icon in services_data:
            service = Service.objects.filter(title=old_title).first() \
                or Service.objects.filter(title=new_title).first()
            if service:
                service.title = new_title
                service.summary = summary
                service.description = description
                service.icon = icon
                service.is_active = True
                service.save()
            else:
                Service.objects.create(
                    title=new_title, summary=summary, description=description,
                    icon=icon, is_active=True,
                )
            updated += 1
        self.stdout.write(
            f"Updated {updated} Service rows with real Services-page copy "
            "(Cloud Migration & DevOps, Mobile App Development, Security Audits "
            "& Compliance, and Technical Training & Upskilling were left as-is, "
            "not covered by the document's 6-service Services page)."
        )

    # ── Resources/Blog page categories ───────────────────────────────────────
    def _seed_blog_categories(self):
        # (old name to match on a first run, new name, description, icon)
        categories_data = [
            (
                "Software Engineering", "Software Development",
                "Programming, frameworks, architecture, testing, and software "
                "engineering practices.",
                "code",
            ),
            (
                "Cybersecurity", "Cybersecurity Insights",
                "Security awareness, secure application development, risk "
                "management, and cybersecurity education.",
                "shield",
            ),
            (
                "AI & Data", "AI & Data",
                "Artificial intelligence, machine learning, analytics, and "
                "data-driven solutions.",
                "brain-circuit",
            ),
        ]
        for old_name, new_name, description, icon in categories_data:
            category = BlogCategory.objects.filter(name=old_name).first() \
                or BlogCategory.objects.filter(name=new_name).first()
            if category:
                category.name = new_name
                category.description = description
                category.icon = icon
                category.is_active = True
                category.save()
            else:
                BlogCategory.objects.create(
                    name=new_name, description=description, icon=icon, is_active=True,
                )

        # New categories from the document not already represented.
        new_categories_data = [
            (
                "Technology Education", "graduation-cap",
                "Learning resources, training updates, career development, and "
                "ICT skills.",
            ),
            (
                "Business Technology", "briefcase",
                "Digital transformation, business applications, and technology "
                "adoption.",
            ),
        ]
        for name, icon, description in new_categories_data:
            BlogCategory.objects.update_or_create(
                name=name, defaults={"description": description, "icon": icon, "is_active": True},
            )

        self.stdout.write(
            f"Updated/added {len(categories_data) + len(new_categories_data)} "
            "BlogCategory rows to match the 5 Resources-page categories "
            "(Cloud & DevOps and Career Advice were left as-is, not part of "
            "the document's category list)."
        )

    # ── Digital Solutions → shown on the Projects & Portfolio page ──────────
    def _seed_digital_solutions(self):
        """
        The document's "Digital Solutions" page describes AbrayTech's own
        product lineup (DigitalMedics, DigitalCampus, etc.); there's no
        Digital Solutions page/model in this codebase, so per instruction
        these are seeded as Project rows instead, appearing on the existing
        Projects & Portfolio page. Not marked is_featured (that carousel
        stays reserved for real client work), but given a low `order` so
        they lead the Projects listing ahead of the older demo entries.
        """
        software_service = Service.objects.filter(title="Custom Software Development").first()

        solutions_data = [
            (
                "DigitalMedics",
                "Electronic Medical Records (EMR) & Healthcare Management.",
                "Healthcare organizations need digital records, operational "
                "workflows, and healthcare management capabilities in place of "
                "paper-based or disconnected systems.",
                "DigitalMedics is designed to support healthcare organizations "
                "with digital records, operational workflows, and healthcare "
                "management capabilities. Potential feature areas: electronic "
                "medical records, patient management, appointment and booking "
                "workflows, healthcare administration, and reporting and "
                "operational insights.",
            ),
            (
                "DigitalCampus",
                "Intelligent Learning Management & Computer-Based Testing.",
                "Education and training organizations need a technology "
                "platform to support learning delivery, assessment, and "
                "administration.",
                "DigitalCampus provides a technology platform for education "
                "and training organizations, supporting learning delivery, "
                "assessment, and administration. Feature areas: learning "
                "management system, computer-based testing, course and "
                "learner management, educational resources, and assessment "
                "workflows.",
            ),
            (
                "DigitalHotels",
                "Hotel & Lounge Management.",
                "Hospitality businesses need to manage their daily operations "
                "through an integrated digital system rather than manual or "
                "fragmented tools.",
                "DigitalHotels is designed to help hospitality businesses "
                "manage their daily operations through an integrated digital "
                "system. Feature areas: hotel operations management, booking "
                "and reservation workflows, guest management, lounge "
                "operations, and business reporting.",
            ),
            (
                "DigitalPharmacy",
                "Pharmacy & Chemist Management.",
                "Pharmacies and chemists need digital tools for managing "
                "business activities and improving operational organization.",
                "DigitalPharmacy supports pharmacies and chemists with digital "
                "tools for managing business activities and improving "
                "operational organization. Feature areas: product and "
                "inventory management, sales management, customer records, "
                "reporting, and pharmacy workflow support.",
            ),
            (
                "DigitalSale",
                "Business Management & Point-of-Sale.",
                "Businesses need to manage sales, products, inventory, and "
                "day-to-day operations through an accessible business "
                "management system.",
                "DigitalSale is designed to help businesses manage sales, "
                "products, inventory, and day-to-day operations through an "
                "accessible business management system. Feature areas: "
                "point-of-sale functionality, product management, inventory "
                "tracking, sales reporting, and business operations.",
            ),
        ]

        for order, (title, summary, challenge, solution_text) in enumerate(solutions_data, start=1):
            Project.objects.update_or_create(
                title=title,
                defaults={
                    "summary": summary,
                    "client_name": "",
                    "service": software_service,
                    "challenge": challenge,
                    "solution_text": solution_text,
                    "results": (
                        "One of AbrayTech's own in-house digital products. "
                        "feature availability reflects the current implemented "
                        "application."
                    ),
                    "is_featured": False,
                    "is_active": True,
                    "order": order,
                },
            )
        self.stdout.write(
            f"Seeded {len(solutions_data)} Digital Solutions as Project rows "
            "(DigitalMedics, DigitalCampus, DigitalHotels, DigitalPharmacy, "
            "DigitalSale), visible on the Projects & Portfolio page."
        )
