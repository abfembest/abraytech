"""
Management command: seed_courses
Usage: python manage.py seed_courses

Seeds ONLY the academic-structure tables:
  - Faculty
  - Department
  - Program
  - Course  (10-11+ realistic courses per program, per level/semester)

NOTE: This command wipes and re-seeds ONLY the tables listed above.
      It does NOT touch Users, SiteConfig, Sessions, Enrollments, etc.
"""

import random
from decimal import Decimal
from faker import Faker
from django.core.management.base import BaseCommand
from eduweb.models import Faculty, Department, Program, Course

fake = Faker()


class Command(BaseCommand):
    help = 'Seeds Faculties, Departments, Programs, and academic Courses with realistic data.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING('🎓 Seeding academic course structure...'))

        # ── CLEANUP ──────────────────────────────────────────────────────────
        self.stdout.write('🧹 Clearing existing course-structure data...')
        Course.objects.all().delete()
        Program.objects.all().delete()
        Department.objects.all().delete()
        Faculty.objects.all().delete()
        self.stdout.write(self.style.SUCCESS('   ✅ Cleared'))

        # ══════════════════════════════════════════════════════════════════════
        # 1. FACULTIES
        # ══════════════════════════════════════════════════════════════════════
        self.stdout.write('🏛️  Creating faculties...')
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
                    'Bloomberg Terminal Lab',
                    'Executive mentorship programme',
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
                    'Annual Arts Festival',
                    'Partnerships with national museums',
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
        self.stdout.write(self.style.SUCCESS(f'   ✅ {len(faculties)} faculties created'))

        # ══════════════════════════════════════════════════════════════════════
        # 2. DEPARTMENTS
        # ══════════════════════════════════════════════════════════════════════
        self.stdout.write('🏛️  Creating departments...')
        # faculties[0]=CSIT  faculties[1]=ENG  faculties[2]=BUS
        # faculties[3]=HLTH  faculties[4]=ART
        dept_raw = [
            # index 0
            (faculties[0], 'Department of Software Engineering', 'SE',
             'Focuses on design, development, and maintenance of software systems.', 0),
            # index 1
            (faculties[0], 'Department of Artificial Intelligence', 'AI',
             'Research and teaching at the frontier of AI and machine learning.', 1),
            # index 2
            (faculties[0], 'Department of Cybersecurity', 'CYS',
             'Specialists in network security, ethical hacking, and digital forensics.', 2),
            # index 3
            (faculties[1], 'Department of Civil Engineering', 'CVE',
             'Structural design, environmental systems, and infrastructure engineering.', 0),
            # index 4
            (faculties[1], 'Department of Electrical Engineering', 'EEE',
             'Power systems, electronics, and telecommunications engineering.', 1),
            # index 5
            (faculties[1], 'Department of Mechanical Engineering', 'MEE',
             'Thermodynamics, manufacturing, and mechanical design.', 2),
            # index 6
            (faculties[2], 'Department of Finance & Accounting', 'FNA',
             'Financial analysis, corporate finance, and accounting standards.', 0),
            # index 7
            (faculties[2], 'Department of Marketing & Strategy', 'MKS',
             'Brand management, consumer behaviour, and corporate strategy.', 1),
            # index 8
            (faculties[2], 'Department of Entrepreneurship', 'ENT',
             'Startup ecosystems, innovation management, and venture creation.', 2),
            # index 9
            (faculties[3], 'Department of Nursing', 'NRS',
             'Adult, child, and mental health nursing education and practice.', 0),
            # index 10
            (faculties[3], 'Department of Public Health', 'PHE',
             'Epidemiology, health policy, and community health management.', 1),
            # index 11
            (faculties[4], 'Department of English & Creative Writing', 'ECW',
             'Literature, linguistics, and creative and professional writing.', 0),
            # index 12
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
        self.stdout.write(self.style.SUCCESS(f'   ✅ {len(departments)} departments created'))

        # ══════════════════════════════════════════════════════════════════════
        # 3. PROGRAMS
        # ══════════════════════════════════════════════════════════════════════
        self.stdout.write('📖 Creating programs...')
        # (dept, name, code, degree_level, duration_years, credits_required,
        #  app_fee, tuition_fee, max_students, is_featured, display_order)
        prog_raw = [
            # index 0 — CSIT / SE
            (departments[0], 'BSc Software Engineering', 'BSC-SE', 'undergraduate',
             Decimal('3.0'), 360, Decimal('50.00'), Decimal('9250.00'), 80, True, 0),
            # index 1
            (departments[0], 'MSc Advanced Software Engineering', 'MSC-ASE', 'masters',
             Decimal('1.0'), 180, Decimal('75.00'), Decimal('14500.00'), 40, False, 1),
            # index 2 — CSIT / AI
            (departments[1], 'BSc Artificial Intelligence', 'BSC-AI', 'undergraduate',
             Decimal('3.0'), 360, Decimal('50.00'), Decimal('9250.00'), 60, True, 0),
            # index 3
            (departments[1], 'PhD Artificial Intelligence', 'PHD-AI', 'phd',
             Decimal('4.0'), 480, Decimal('100.00'), Decimal('18000.00'), 15, False, 1),
            # index 4 — CSIT / CYS
            (departments[2], 'BSc Cybersecurity', 'BSC-CYS', 'undergraduate',
             Decimal('3.0'), 360, Decimal('50.00'), Decimal('9250.00'), 50, False, 0),
            # index 5 — ENG / CVE
            (departments[3], 'BEng Civil Engineering', 'BENG-CVE', 'undergraduate',
             Decimal('4.0'), 480, Decimal('50.00'), Decimal('9250.00'), 70, True, 0),
            # index 6 — ENG / EEE
            (departments[4], 'BEng Electrical Engineering', 'BENG-EEE', 'undergraduate',
             Decimal('4.0'), 480, Decimal('50.00'), Decimal('9250.00'), 60, False, 0),
            # index 7 — BUS / FNA
            (departments[6], 'BSc Finance & Accounting', 'BSC-FNA', 'undergraduate',
             Decimal('3.0'), 360, Decimal('50.00'), Decimal('9250.00'), 75, True, 0),
            # index 8
            (departments[6], 'MBA Finance', 'MBA-FIN', 'masters',
             Decimal('1.0'), 180, Decimal('100.00'), Decimal('17500.00'), 35, True, 1),
            # index 9 — HLTH / NRS
            (departments[9], 'BSc Nursing', 'BSC-NRS', 'undergraduate',
             Decimal('3.0'), 360, Decimal('50.00'), Decimal('9250.00'), 80, True, 0),
            # index 10 — ART / ECW
            (departments[11], 'BA English & Creative Writing', 'BA-ECW', 'undergraduate',
             Decimal('3.0'), 360, Decimal('50.00'), Decimal('9250.00'), 60, False, 0),
            # index 11 — ART / DMD
            (departments[12], 'BA Digital Media & Design', 'BA-DMD', 'undergraduate',
             Decimal('3.0'), 360, Decimal('50.00'), Decimal('9250.00'), 50, False, 0),
        ]
        programs = []
        for (dept, name, code, degree, dur, cred, app_fee, tuit, max_stu, feat, order) in prog_raw:
            base_name = name.split()[-1]
            _sem_cap = 18 if degree == 'undergraduate' else (
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
        self.stdout.write(self.style.SUCCESS(f'   ✅ {len(programs)} programs created'))

        # ══════════════════════════════════════════════════════════════════════
        # 4. ACADEMIC COURSES
        # Format: (program, course_type, code, name, year, semester, credits,
        #          icon, color_primary, color_secondary)
        # ══════════════════════════════════════════════════════════════════════
        self.stdout.write('📚 Creating academic courses...')

        ac_raw = [

            # ──────────────────────────────────────────────────────────────────
            # programs[0]  BSc Software Engineering  (3 years, 2 semesters)
            # ──────────────────────────────────────────────────────────────────
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

            # ──────────────────────────────────────────────────────────────────
            # programs[1]  MSc Advanced Software Engineering  (1 year, PG)
            # ──────────────────────────────────────────────────────────────────
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

            # ──────────────────────────────────────────────────────────────────
            # programs[2]  BSc Artificial Intelligence  (3 years)
            # ──────────────────────────────────────────────────────────────────
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

            # ──────────────────────────────────────────────────────────────────
            # programs[3]  PhD Artificial Intelligence  (4 years)
            # ──────────────────────────────────────────────────────────────────
            (programs[3], 'core',     'PHD701', 'Doctoral Research Methodology',              1, 'first',  6, 'file-text',      'gray',   'slate'),
            (programs[3], 'core',     'PHD702', 'Advanced Machine Learning Theory',           1, 'first',  6, 'brain',          'purple', 'violet'),
            (programs[3], 'elective', 'PHD703', 'Research Seminar Series I',                  1, 'second', 4, 'mic',            'blue',   'indigo'),
            (programs[3], 'elective', 'PHD704', 'Advanced Deep Learning',                     1, 'second', 6, 'network',        'violet', 'indigo'),
            (programs[3], 'core',     'PHD705', 'PhD Thesis (Year 1 Progress)',               1, 'second', 8, 'scroll',         'gray',   'blue'),
            (programs[3], 'core',     'PHD801', 'PhD Thesis (Year 2 Research)',               2, 'first', 12, 'scroll',         'gray',   'blue'),
            (programs[3], 'elective', 'PHD802', 'Research Seminar Series II',                 2, 'second', 4, 'mic',            'blue',   'sky'),
            (programs[3], 'core',     'PHD901', 'PhD Thesis (Year 3 Writing)',                3, 'first', 12, 'scroll',         'gray',   'blue'),
            (programs[3], 'elective', 'PHD902', 'Academic Publication & Dissemination',       3, 'second', 4, 'book-open',      'green',  'teal'),
            (programs[3], 'core',     'PHD001', 'PhD Thesis Submission & Viva',               4, 'second',12, 'award',          'amber',  'yellow'),

            # ──────────────────────────────────────────────────────────────────
            # programs[4]  BSc Cybersecurity  (3 years)
            # ──────────────────────────────────────────────────────────────────
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

            # ──────────────────────────────────────────────────────────────────
            # programs[5]  BEng Civil Engineering  (4 years)
            # ──────────────────────────────────────────────────────────────────
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
            (programs[5], 'elective', 'CVE109', 'Soil Mechanics Introduction',                1, 'second', 3, 'mountain',       'amber',  'yellow'),
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

            # ──────────────────────────────────────────────────────────────────
            # programs[6]  BEng Electrical Engineering  (4 years)
            # ──────────────────────────────────────────────────────────────────
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

            # ──────────────────────────────────────────────────────────────────
            # programs[7]  BSc Finance & Accounting  (3 years)
            # ──────────────────────────────────────────────────────────────────
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

            # ──────────────────────────────────────────────────────────────────
            # programs[8]  MBA Finance  (1 year, PG)
            # ──────────────────────────────────────────────────────────────────
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

            # ──────────────────────────────────────────────────────────────────
            # programs[9]  BSc Nursing  (3 years)
            # ──────────────────────────────────────────────────────────────────
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

            # ──────────────────────────────────────────────────────────────────
            # programs[10]  BA English & Creative Writing  (3 years)
            # ──────────────────────────────────────────────────────────────────
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
            (programs[10], 'elective', 'ECW111', 'Introduction to Drama Studies',             1, 'second', 3, 'film',           'pink',   'rose'),
            (programs[10], 'elective', 'ECW112', 'Digital Reading & Media Literacy',          1, 'second', 3, 'monitor',        'sky',    'blue'),
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
            (programs[10], 'elective', 'ECW209', 'Satire & Irony in Literature',              2, 'second', 3, 'pen',            'amber',  'yellow'),
            (programs[10], 'elective', 'ECW210', 'Translation Studies',                       2, 'second', 3, 'globe',          'teal',   'emerald'),
            # Year 3 — Semester 1
            (programs[10], 'elective', 'ECW301', 'Screenwriting & Drama',                     3, 'first',  3, 'film',           'pink',   'rose'),
            (programs[10], 'elective', 'ECW303', 'Gothic & Horror Fiction',                   3, 'first',  3, 'moon',           'gray',   'slate'),
            (programs[10], 'elective', 'ECW304', 'Travel Writing & Memoir',                   3, 'first',  3, 'map',            'amber',  'orange'),
            (programs[10], 'elective', 'ECW305', 'Contemporary Poetry Writing',               3, 'first',  3, 'feather',        'purple', 'fuchsia'),
            # Year 3 — Semester 2
            (programs[10], 'core',     'ECW302', 'Dissertation in English',                   3, 'second', 6, 'scroll',         'gray',   'purple'),
            (programs[10], 'elective', 'ECW306', "Children's Literature & Writing",           3, 'second', 3, 'book-open',      'pink',   'rose'),
            (programs[10], 'elective', 'ECW307', 'Advanced Novel Writing',                    3, 'second', 3, 'pen',            'violet', 'indigo'),

            # ──────────────────────────────────────────────────────────────────
            # programs[11]  BA Digital Media & Design  (3 years)
            # ──────────────────────────────────────────────────────────────────
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
        for idx, (prog, ctype, code, name, year, semester, credits, icon, col1, col2) in enumerate(ac_raw):
            c = Course.objects.create(
                program=prog,
                name=name,
                code=code,
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
                display_order=idx,
            )
            academic_courses.append(c)

        # ── SUMMARY ───────────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 60))
        self.stdout.write(self.style.SUCCESS('✅  COURSE STRUCTURE SEEDING COMPLETE'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        rows = [
            ('Faculties',    Faculty.objects.count()),
            ('Departments',  Department.objects.count()),
            ('Programs',     Program.objects.count()),
            ('Courses',      Course.objects.count()),
        ]
        for label, count in rows:
            self.stdout.write(f'   {label:<20} {count}')

        # Per-program breakdown
        self.stdout.write('\n   Courses per program:')
        for p in Program.objects.all().order_by('code'):
            cnt = Course.objects.filter(program=p).count()
            self.stdout.write(f'     [{p.code}] {p.name:<45} {cnt} courses')

        self.stdout.write(self.style.SUCCESS('=' * 60 + '\n'))