"""
Seed the backend academic data (Program + Course rows) for the six real
AbrayTech Academy training programmes described in
"AbrayTech Website Content Development.docx" ("COURSE CONTENTS" section):

  1. Python Software Development & Programming     (7-month Professional Programme)
  2. Cybersecurity Analyst Professional Programme   (7-month Professional Programme)
  3. Data Analytics Professional Programme          (7-month Professional Programme)
  4. Mobile App Development Using React Native      (8-month Professional Programme)
  5. AI & Machine Learning Using Python             (8-month Professional Programme)
  6. Cybersecurity Governance, Risk & Compliance    (8-month Professional Programme)

Companion command: `seed_public` seeds the homepage/About/Services/
Resources copy from the same document; run both to fully apply it.

Standalone: creates its own Faculty/Department rows if they don't already
exist, so this command works on a completely fresh database with no other
seed command needed first. Every identity here, not just the programmes,
is taken from the document itself rather than an unrelated demo scheme:

  - Three Faculties, one per the document's own "Training categories"
    (Section 6): Software Development, Cybersecurity, and Data & AI. Each
    is its own top-level section on the programs page (all_programs.html
    groups by Faculty first), so the three tracks show up separated from
    each other rather than nested under one shared umbrella.
  - One same-named Department under each Faculty (this codebase requires
    Program -> Department -> Faculty; the document itself doesn't split
    department from faculty, so each track is kept as a single level).
  - Six Programs, one per real programme, with codes derived from each
    programme's own name (PSD, CSA, DAP, MAD, AIM, CGR) rather than any
    pre-existing demo Program code.

Programme to faculty/department mapping:
    Python Software Development & Programming (PSD) -> Software Development
    Mobile App Development Using React Native  (MAD) -> Software Development
    Cybersecurity Analyst Professional Programme (CSA) -> Cybersecurity
    Cybersecurity Governance, Risk & Compliance  (CGR) -> Cybersecurity
    Data Analytics Professional Programme        (DAP) -> Data & AI
    AI & Machine Learning Using Python           (AIM) -> Data & AI

Idempotent: safe to re-run. Faculties/Departments are matched by code,
Programs by (department, code), and Courses by (program, code), then
updated in place.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.eduweb.models import Faculty, Department, Program, Course


# Faculty/Department rows this command needs to attach its 6 programmes to,
# named and worded straight from the document's own "Training categories"
# list and its per-category topic bullets, not from any pre-existing demo
# data. Each is its own Faculty (see module docstring) so the programs page
# shows Software Development, Cybersecurity, and Data & AI as three
# separate top-level sections instead of one combined "Academy" block.
FACULTIES = {
    "SWD": {
        "name": "Software Development",
        "tagline": "Programming, web development, and software engineering fundamentals.",
        "description": (
            "Part of AbrayTech Academy's technology skills training: "
            "practical programming, web development, database development, "
            "and software engineering fundamentals."
        ),
    },
    "CYB": {
        "name": "Cybersecurity",
        "tagline": "Defend, investigate, and secure digital environments.",
        "description": (
            "Part of AbrayTech Academy's technology skills training: "
            "cybersecurity fundamentals, network security, secure software "
            "development, and web application security."
        ),
    },
    "DAI": {
        "name": "Data & AI",
        "tagline": "Turn data into decisions with analytics, machine learning, and AI.",
        "description": (
            "Part of AbrayTech Academy's technology skills training: "
            "data analytics, Python for data science, Power BI, machine "
            "learning fundamentals, and applied artificial intelligence."
        ),
    },
}

DEPARTMENTS = {
    "SWD": {"faculty_code": "SWD", "name": "Software Development"},
    "CYB": {"faculty_code": "CYB", "name": "Cybersecurity"},
    "DAI": {"faculty_code": "DAI", "name": "Data & AI"},
}


def get_or_create_department(dept_code):
    dept_info = DEPARTMENTS[dept_code]
    faculty_info = FACULTIES[dept_info["faculty_code"]]
    faculty, _ = Faculty.objects.get_or_create(
        code=dept_info["faculty_code"],
        defaults={
            "name": faculty_info["name"],
            "tagline": faculty_info["tagline"],
            "description": faculty_info["description"],
        },
    )
    department, _ = Department.objects.get_or_create(
        faculty=faculty, code=dept_code,
        defaults={"name": dept_info["name"]},
    )
    return department


# Generic, non-overpromising entry requirements. The document explicitly
# warns against inventing a fixed application/review timeline, so this
# sticks to what its "Learning process" section actually describes.
ENTRY_REQUIREMENTS = [
    "No formal academic prerequisites; the programme is designed for beginners as well as working professionals",
    "Basic computer literacy and a reliable internet connection",
    "Completion of the AbrayTech Academy application, and any programme-specific assessment or interview",
]


def scheme_of_work(objective, modules, capstone_title, capstone_desc):
    """
    Render a Course.description in the exact convention Course.scheme_of_work()
    parses for the program-detail curriculum accordion: any plain line opens
    a new section header, and a line starting "N.N " is a bullet item under
    the current header.
    """
    lines = [objective, ""]
    for i, (module_name, topics) in enumerate(modules, start=1):
        lines.append(module_name)
        lines.append(f"{i}.1 " + ", ".join(topics))
    lines.append(f"Capstone: {capstone_title}")
    lines.append(f"{len(modules) + 1}.1 {capstone_desc}")
    return "\n".join(lines)


# =============================================================================
# PROGRAMME 1: Python Software Development & Programming (7 months)
# =============================================================================
PYTHON_SOFTWARE_DEV = {
    "dept_code": "SWD",
    "code": "PSD",
    "name": "Python Software Development & Programming",
    "tagline": "Learn Python. Build Real Applications. Develop Professional Software Engineering Skills.",
    "overview": (
        "An 8-12 hour/week professional programme that takes learners from absolute "
        "beginner to advanced software development. By the end, learners should be "
        "able to design, develop, test, secure, deploy, and maintain real-world "
        "Python applications, not simply write Python syntax. The final months are "
        "heavily project-based, with a substantial capstone each month."
    ),
    "description": (
        "The Python Software Development & Programming Professional Programme "
        "progresses through three stages: Beginner (Months 1-2, programming "
        "fundamentals and Python), Intermediate (Months 3-4, software development, "
        "databases, APIs, and the first major project), and Advanced (Months 5-7, "
        "web development, architecture, security, deployment, and professional "
        "projects).\n\n"
        "Learners finish the programme with four substantial portfolio projects: a "
        "Django business management web app, a healthcare appointment & patient "
        "management system, a secure e-commerce marketplace, and an AI-powered "
        "business intelligence platform, rather than one project at the end."
    ),
    "career_paths": [
        "Junior Software Developer", "Python Developer", "Backend Developer",
        "Full-Stack Developer (Django)", "Software Engineer", "API Developer",
    ],
    "learning_outcomes": [
        "Programming: Python, object-oriented programming, data structures, algorithms, exception handling, file processing, APIs, async programming fundamentals",
        "Web Development: HTML, CSS, JavaScript fundamentals, Django, Django REST Framework, REST APIs",
        "Databases: SQL, PostgreSQL, SQLite, database design, ORM, query optimization",
        "Software Engineering: Git, GitHub, clean code, SOLID principles, design patterns, testing, documentation, Agile development",
        "Cybersecurity: secure coding, authentication, authorization, OWASP fundamentals, secure APIs, application security",
        "DevOps: Linux, Nginx, Gunicorn, Docker, CI/CD, deployment, monitoring, backups",
        "AI & Data: Pandas, NumPy, data visualisation, Scikit-learn, machine learning fundamentals, AI application integration",
    ],
    "months": [
        {
            "title": "Month 1: Python & Programming Fundamentals",
            "objective": "Introduce learners to programming concepts and establish a strong Python foundation.",
            "modules": [
                ("Module 1: Introduction to Programming", ["what is programming", "programming languages", "compilers vs interpreters", "algorithms and problem solving", "flowcharts", "pseudocode", "variables and data", "input to processing to output", "introduction to debugging"]),
                ("Module 2: Python Fundamentals", ["installing Python", "the Python interpreter", "IDEs and code editors", "Python syntax", "comments", "variables", "naming conventions", "data types: str, int, float, bool, None"]),
                ("Module 3: Operators", ["arithmetic operators", "comparison operators", "logical operators", "assignment operators", "membership operators", "identity operators", "operator precedence"]),
                ("Module 4: Input and Output", ["print()", "input()", "type conversion", "string formatting", "f-strings", "basic validation"]),
                ("Module 5: Conditional Programming", ["if / elif / else", "nested conditions", "Boolean expressions", "decision-making programs"]),
                ("Module 6: Loops", ["for", "while", "range()", "nested loops", "break", "continue", "pass"]),
            ],
            "capstone_title": "Personal Finance Calculator",
            "capstone_desc": "A command-line application that records income and expenses, categorises them, and calculates total expenditure, remaining balance, and savings percentage, demonstrating syntax, variables, operators, conditions, loops, functions, and input validation.",
        },
        {
            "title": "Month 2: Core Python Programming",
            "objective": "Move from basic syntax to structured programming.",
            "modules": [
                ("Module 1: Functions", ["defining functions", "parameters and arguments", "return values", "default parameters", "keyword arguments", "variable scope", "lambda functions", "docstrings"]),
                ("Module 2: Data Structures", ["lists (creating, indexing, slicing, methods, comprehensions)", "tuples (creation, unpacking, operations)", "sets (union, intersection, difference)", "dictionaries (key/value structures, methods, nested dictionaries, comprehensions)"]),
                ("Module 3: Working With Strings", ["string methods", "searching", "splitting", "joining", "formatting", "regular expressions introduction"]),
                ("Module 4: Files", ["reading and writing files", "CSV files", "JSON files", "file paths", "exception handling"]),
                ("Module 5: Error Handling", ["errors vs exceptions", "try / except / else / finally", "raising exceptions", "custom exceptions"]),
                ("Module 6: Python Modules", ["importing modules", "creating modules", "packages", "standard library", "pip", "virtual environments"]),
            ],
            "capstone_title": "Student Management System",
            "capstone_desc": "A Python application allowing an administrator to add, update, delete, and search students, record courses and grades, calculate averages, generate reports, and save data to JSON/CSV.",
        },
        {
            "title": "Month 3: Object-Oriented Programming, Git & Databases",
            "objective": "Introduce professional programming practices and persistent data storage.",
            "modules": [
                ("Module 1: Object-Oriented Programming", ["classes", "objects", "attributes", "methods", "constructors", "encapsulation", "inheritance", "polymorphism", "abstraction", "composition"]),
                ("Module 2: Advanced Python", ["iterators", "generators", "decorators", "context managers", "*args and **kwargs", "type hints", "dataclasses"]),
                ("Module 3: Software Development Practices", ["clean code", "the DRY principle", "separation of concerns", "modular architecture", "naming conventions", "documentation", "requirements gathering"]),
                ("Module 4: Git & GitHub", ["Git fundamentals", "repository creation", "commits", "branches", "merging", "pull requests", ".gitignore", "GitHub repositories", "collaboration", "resolving conflicts"]),
                ("Module 5: Databases", ["SQL fundamentals: tables, records, primary/foreign keys, relationships, CRUD", "SQL: SELECT, INSERT, UPDATE, DELETE, WHERE, JOIN, GROUP BY, ORDER BY, aggregation", "Python database integration: SQLite, connections, queries, transactions"]),
            ],
            "capstone_title": "Business Inventory & Sales Management System",
            "capstone_desc": "A CLI application managing products, categories, customers, and suppliers, with stock management, sales transactions with automatic stock updates, sales reports, and database persistence. Learners must use Git throughout development.",
        },
        {
            "title": "Month 4: Web Development, APIs & Django",
            "objective": "Teach learners how to transform Python knowledge into real web applications. This marks the beginning of the 4-month practical project phase.",
            "modules": [
                ("Module 1: Web Fundamentals", ["how the internet works", "HTTP/HTTPS", "request/response", "URLs and domains", "web servers", "client/server architecture", "REST APIs"]),
                ("Module 2: HTML & CSS Fundamentals", ["HTML structure", "forms", "tables", "semantic HTML", "CSS selectors", "layout", "responsive design", "basic JavaScript concepts"]),
                ("Module 3: Django", ["Django architecture", "project creation", "applications", "URLs", "views", "templates", "models", "migrations", "Django ORM", "forms", "static and media files", "Django Admin"]),
                ("Module 4: Authentication", ["registration", "login/logout", "password management", "user permissions", "groups", "role-based access"]),
                ("Module 5: APIs", ["API concepts", "JSON", "REST", "HTTP methods", "API authentication", "Django REST Framework introduction"]),
            ],
            "capstone_title": "Business Management Web Application",
            "capstone_desc": "A complete Django application for a small business: authentication (registration/login/logout/password reset), a dashboard (sales summary, products, customers, stock, recent transactions), product management (add/edit/delete/search/categories), sales (create sales, generate totals, update stock, sales history), reporting (daily/monthly sales, product performance), and a REST API exposing selected business data. Deliverable: a functioning, documented Django application stored in GitHub.",
        },
        {
            "title": "Month 5: Advanced Django & Professional Web Applications",
            "objective": "Move from basic Django applications to production-oriented systems.",
            "modules": [
                ("Module 1: Advanced Django", ["class-based views", "custom user models", "model relationships", "query optimization", "advanced ORM", "signals", "middleware", "custom management commands"]),
                ("Module 2: Advanced Authentication", ["role-based access control", "permissions", "staff accounts", "API authentication", "token authentication", "session management"]),
                ("Module 3: Advanced APIs", ["Django REST Framework", "serializers", "viewsets", "routers", "permissions", "pagination", "filtering", "API documentation"]),
                ("Module 4: Background Processing", ["Celery", "Redis", "scheduled tasks", "background jobs", "email processing"]),
                ("Module 5: Testing", ["unit testing", "integration testing", "Django testing", "test-driven development introduction", "test coverage", "debugging"]),
            ],
            "capstone_title": "Healthcare Appointment & Patient Management System",
            "capstone_desc": "A realistic healthcare application: patients (registration, profiles, search, records), appointments (booking, rescheduling, cancellation, history), healthcare staff (doctor/staff accounts, role-based permissions), a dashboard (appointments, patient statistics, operational summaries), and email appointment-reminder notifications, plus REST APIs for selected functionality. Advanced requirements: PostgreSQL, authentication, RBAC, automated tests, Git/GitHub, and API documentation.",
        },
        {
            "title": "Month 6: Software Engineering, Security, DevOps & Deployment",
            "objective": "Teach learners how professional software is secured, tested, deployed, and maintained.",
            "modules": [
                ("Module 1: Secure Software Development", ["OWASP principles", "authentication security", "authorization", "password security", "input validation", "SQL injection", "XSS", "CSRF", "session security", "secure file uploads", "secrets management"]),
                ("Module 2: Application Security", ["security headers", "HTTPS", "environment variables", "access control", "logging", "audit trails", "rate limiting", "secure APIs"]),
                ("Module 3: DevOps Fundamentals", ["Linux fundamentals", "servers", "SSH", "environment configuration", "Git deployment", "Nginx", "Gunicorn", "PostgreSQL"]),
                ("Module 4: Docker", ["containers", "images", "Dockerfiles", "Docker Compose", "container networking", "persistent volumes"]),
                ("Module 5: CI/CD", ["continuous integration", "automated testing", "GitHub Actions", "deployment pipelines", "environment management"]),
                ("Module 6: Monitoring & Maintenance", ["application logs", "error monitoring", "backups", "database maintenance", "performance monitoring"]),
            ],
            "capstone_title": "Secure E-Commerce & Online Marketplace",
            "capstone_desc": "A production-style online marketplace with customer functionality (registration, login, product browsing/search/categories, shopping basket, checkout, order history), business functionality (product management, inventory, orders, customers, sales dashboard, reports), security (secure authentication, RBAC, CSRF protection, secure uploads, input validation, rate limiting, security headers), and DevOps (Docker, PostgreSQL, Nginx, Gunicorn, CI/CD, HTTPS). Final deliverable: a deployed application with a GitHub repository, README, documentation, automated tests, deployment instructions, and a security checklist.",
        },
        {
            "title": "Month 7: Advanced Python, AI/Data & Professional Software Engineering",
            "objective": "Bring together the entire programme through a sophisticated final project while introducing modern Python applications in AI and data. This is the final graduation project.",
            "modules": [
                ("Module 1: Advanced Python Architecture", ["design patterns", "SOLID principles", "dependency management", "application architecture", "service layers", "repository patterns", "modular systems"]),
                ("Module 2: Data Processing", ["NumPy", "Pandas", "data cleaning", "data transformation", "data visualisation"]),
                ("Module 3: Machine Learning Introduction", ["machine learning concepts", "supervised and unsupervised learning", "feature engineering", "model training", "model evaluation", "Scikit-learn"]),
                ("Module 4: AI Application Development", ["integrating AI into applications", "AI APIs", "prompt engineering fundamentals", "AI-assisted workflows", "recommendation systems", "intelligent search"]),
                ("Module 5: Performance & Scalability", ["database optimization", "caching", "Redis", "query optimization", "asynchronous programming", "application scalability"]),
                ("Module 6: Professional Development", ["software documentation", "technical presentations", "code reviews", "GitHub portfolio", "CV/project portfolio", "interview preparation", "freelancing/project estimation", "requirements gathering", "Agile development"]),
            ],
            "capstone_title": "AI-Powered Business Intelligence Platform",
            "capstone_desc": "The final graduation project is an intelligent platform allowing businesses to upload or connect business data and obtain useful insights: user management, data upload/validation/cleaning (CSV/Excel), analytics (KPIs, charts, reports, trend analysis), AI features (natural-language questions about business data, automated insight generation, anomaly identification, basic predictive analysis, recommendations), an interactive dashboard with filters and exportable reports, and a REST API, deployed with Docker, PostgreSQL, Redis, Nginx, Gunicorn, HTTPS, and CI/CD.",
        },
    ],
}


# =============================================================================
# PROGRAMME 2: Cybersecurity Analyst Professional Programme (7 months)
# =============================================================================
CYBERSECURITY_ANALYST = {
    "dept_code": "CYB",
    "code": "CSA",
    "name": "Cybersecurity Analyst Professional Programme",
    "tagline": "Learn cybersecurity. Investigate threats. Respond to incidents. Protect digital environments.",
    "overview": (
        "Build practical cybersecurity skills through hands-on labs, security "
        "investigations, SOC operations, threat intelligence, incident response, "
        "digital forensics, cloud security, and Python-based security automation. "
        "Primary outcome: junior cybersecurity analyst / SOC analyst readiness."
    ),
    "description": (
        "The Cybersecurity Analyst Professional Programme progresses through three "
        "stages: Beginner (Months 1-2, cybersecurity and IT foundations), "
        "Intermediate (Months 3-4, security operations, networks, threats, and the "
        "first major project), and Advanced (Months 5-7, SOC, SIEM, threat "
        "intelligence, incident response, forensics, cloud, and security "
        "automation).\n\n"
        "Learners are assessed on their ability to identify, analyse, investigate, "
        "respond, and document, rather than simply memorise cybersecurity "
        "definitions. The programme finishes with four practical projects of "
        "increasing complexity: a vulnerability assessment, a threat "
        "intelligence investigation, a SOC/SIEM build, and an enterprise "
        "cyber-defence and threat-intelligence platform."
    ),
    "career_paths": [
        "Cybersecurity Analyst", "SOC Analyst", "Security Engineer",
        "Threat Intelligence Analyst", "Incident Response Analyst",
        "Vulnerability Analyst", "Digital Forensics Analyst", "Penetration Tester",
        "Cloud Security Analyst", "GRC Analyst",
    ],
    "learning_outcomes": [
        "Cybersecurity: fundamentals, security controls, risk concepts, security architecture",
        "SOC: alert triage, SIEM, log analysis, detection, incident escalation",
        "Network Security: TCP/IP, DNS, firewalls, IDS/IPS, packet analysis, network monitoring",
        "Threat Intelligence: IOC analysis, threat feeds, STIX/TAXII, MITRE ATT&CK, threat reporting",
        "Vulnerability Management: asset discovery, vulnerability scanning, CVE, CVSS, risk prioritisation, remediation",
        "Incident Response: incident handling, investigation, containment, eradication, recovery, post-incident reporting",
        "Digital Forensics: evidence handling, disk analysis, memory analysis, timeline analysis, Windows/Linux artefacts",
        "Cloud Security: IAM, MFA, cloud security controls, cloud logging, shared responsibility",
        "Security Automation: Python, PowerShell, Bash, APIs, automated IOC enrichment, log processing",
    ],
    "months": [
        {
            "title": "Month 1: Cybersecurity & IT Foundations",
            "objective": "Give learners a strong understanding of computers, networks, operating systems, cybersecurity principles, threats, and security terminology.",
            "modules": [
                ("Module 1: Introduction to Cybersecurity", ["what is cybersecurity", "information security vs cybersecurity", "the CIA Triad (confidentiality, integrity, availability)", "authentication, authorization, accountability, non-repudiation", "security controls (physical, technical, administrative)", "cybersecurity career paths: Analyst, SOC Analyst, Security Engineer, Threat Intelligence Analyst, Incident Response Analyst, Vulnerability Analyst, Digital Forensics Analyst, Penetration Tester, Cloud Security Analyst, GRC Analyst"]),
                ("Module 2: Computer & Operating System Fundamentals", ["Windows: architecture, users and groups, file systems, processes, services, Event Viewer, Registry, PowerShell fundamentals", "Linux: architecture, file system, users and permissions, processes, services, SSH, logs, Bash fundamentals"]),
                ("Module 3: Networking Fundamentals", ["network architecture, LAN/WAN", "the OSI model, TCP/IP, IPv4, IPv6 introduction", "MAC addresses, ARP, DNS, DHCP", "HTTP/HTTPS, FTP, SSH, SMTP", "TCP vs UDP, ports", "firewalls, routers, switches, VPNs"]),
                ("Module 4: Cyber Threat Landscape", ["malware: viruses, worms, trojans, ransomware, spyware", "phishing and social engineering", "credential attacks", "insider threats", "botnets", "denial-of-service attacks", "web attacks", "supply-chain threats"]),
                ("Module 5: Security Fundamentals", ["password security, MFA", "access control, least privilege", "secure configuration, patch management", "backups", "encryption, hashing, digital certificates", "security policies"]),
            ],
            "capstone_title": "Cybersecurity Home Lab",
            "capstone_desc": "Learners build their own isolated cybersecurity laboratory (Windows VM, Linux VM, security testing VM, virtual network, basic firewall configuration) and deliver a network diagram, security configuration, user accounts, firewall rules, security checklist, and lab documentation.",
        },
        {
            "title": "Month 2: Security Operations Fundamentals",
            "objective": "Move from understanding cybersecurity to actually monitoring and analysing security events.",
            "modules": [
                ("Module 1: Security Monitoring", ["security events and logs: event, authentication, network, application, and system logs", "log collection", "log analysis"]),
                ("Module 2: Identity & Access Security", ["authentication, authorization, MFA, RBAC", "privileged accounts, account lifecycle", "password policies", "Active Directory and Group Policy fundamentals"]),
                ("Module 3: Network Security", ["firewalls", "IDS/IPS", "network segmentation", "VPN, proxy, secure DNS", "network monitoring"]),
                ("Module 4: Vulnerability Management", ["vulnerability vs threat vs risk", "CVE, CVSS", "vulnerability scanning, asset discovery", "patch management, risk prioritisation, remediation", "practical tools: Nmap, OpenVAS/Greenbone, Wireshark"]),
                ("Module 5: Cryptography", ["symmetric and asymmetric encryption", "hashing, digital signatures", "PKI", "TLS/SSL, certificates"]),
                ("Module 6: Security Frameworks", ["NIST Cybersecurity Framework", "CIS Controls", "ISO 27001 concepts", "MITRE ATT&CK", "the Cyber Kill Chain"]),
            ],
            "capstone_title": "Vulnerability Assessment & Security Hardening Project",
            "capstone_desc": "Learners receive an intentionally vulnerable lab environment and must discover assets, identify and classify vulnerabilities, assess risk, recommend remediation, apply security hardening, re-test the environment, and produce a professional security report.",
        },
        {
            "title": "Month 3: Threat Analysis, Malware & Threat Intelligence",
            "objective": "Teach learners how analysts identify, understand, investigate, and contextualise threats.",
            "modules": [
                ("Module 1: Threat Intelligence", ["strategic, tactical, operational, and technical intelligence", "indicators of compromise and indicators of attack", "TTPs, threat actors, campaigns"]),
                ("Module 2: MITRE ATT&CK", ["tactics, techniques, sub-techniques, procedures", "attack mapping", "detection mapping"]),
                ("Module 3: Malware Analysis Fundamentals", ["malware lifecycle", "static and dynamic analysis", "file hashes, strings, metadata, PE files", "sandbox and behavioural analysis (safe lab environments only)"]),
                ("Module 4: Network Traffic Analysis", ["using Wireshark for packet capture, TCP streams, DNS/HTTP/TLS traffic analysis", "suspicious connections, beaconing, network anomalies"]),
                ("Module 5: Phishing Analysis", ["email headers, sender authentication (SPF, DKIM, DMARC)", "URLs and attachments", "phishing indicators", "business email compromise"]),
                ("Module 6: Threat Intelligence Platforms", ["STIX, TAXII, OpenCTI, MISP", "open-source intelligence", "threat feeds"]),
            ],
            "capstone_title": "Threat Intelligence Investigation",
            "capstone_desc": "Learners receive a simulated threat campaign and must analyse indicators, investigate domains/IPs/hashes, identify TTPs, map activity to MITRE ATT&CK, create an intelligence report and IOCs, develop detection recommendations, and produce a threat intelligence briefing.",
        },
        {
            "title": "Month 4: SOC Operations & Security Monitoring",
            "objective": "This is the first major professional practical project month. Teach learners how a Security Operations Centre operates and how analysts investigate alerts.",
            "modules": [
                ("Module 1: SOC Fundamentals", ["SOC structure and roles: Tier 1, Tier 2, Tier 3 analyst", "SOC workflows: alert triage, escalation, case management", "security metrics"]),
                ("Module 2: SIEM", ["SIEM concepts and platforms: Microsoft Sentinel, Splunk, Elastic Security, Wazuh", "log ingestion, parsing, searching, dashboards, alerts, detection rules, correlation, investigations"]),
                ("Module 3: Detection Engineering", ["detection logic, rule creation", "false positives, alert tuning", "IOC and behavioural detection", "MITRE ATT&CK mapping"]),
                ("Module 4: Security Alert Investigation", ["investigation scenarios: brute-force login, impossible travel, suspicious PowerShell, malware execution, privilege escalation, suspicious DNS activity, data exfiltration indicators"]),
            ],
            "capstone_title": "SOC Monitoring & Security Operations Centre",
            "capstone_desc": "Learners build a small SOC (endpoints, log collection, SIEM, detection rules, security alerts, analyst investigation, and incident response) and deliver SOC architecture, SIEM deployment, log sources, detection rules, an alert dashboard, incident tickets, investigation reports, MITRE ATT&CK mapping, and a SOC analyst report. Final scenario: detect, triage, investigate, classify, escalate, and document a series of simulated security alerts.",
        },
        {
            "title": "Month 5: Incident Response & Digital Forensics",
            "objective": "Teach learners how to investigate cybersecurity incidents and preserve evidence.",
            "modules": [
                ("Module 1: Incident Response", ["the incident response lifecycle: preparation, detection, analysis, containment, eradication, recovery, lessons learned"]),
                ("Module 2: Incident Classification", ["security event vs security alert vs security incident vs major incident", "severity classification, incident prioritisation"]),
                ("Module 3: Digital Forensics", ["digital evidence, evidence handling, chain of custody", "disk imaging, file systems, memory analysis, timeline analysis", "browser artefacts, event logs"]),
                ("Module 4: Forensic Tools", ["Autopsy", "Volatility", "FTK Imager", "KAPE", "Windows Event Viewer", "Linux forensic utilities"]),
                ("Module 5: Malware Incident Investigation", ["initial compromise, persistence, execution", "command and control", "lateral movement", "data collection, exfiltration"]),
            ],
            "capstone_title": "Cybersecurity Incident Response Investigation",
            "capstone_desc": "A company reports suspicious activity on several endpoints. Learners receive and triage the incident, identify affected systems, analyse logs, examine forensic artefacts, determine the attack timeline, identify IOCs, map activity to MITRE ATT&CK, contain the incident, recommend remediation, and produce a final incident report with an incident timeline, evidence register, IOC list, ATT&CK mapping, root-cause analysis, executive summary, and remediation plan.",
        },
        {
            "title": "Month 6: Cloud Security, Identity & Security Engineering",
            "objective": "Prepare learners to analyse security in modern cloud and enterprise environments.",
            "modules": [
                ("Module 1: Cloud Fundamentals", ["cloud computing", "IaaS, PaaS, SaaS", "the shared responsibility model", "cloud identity, storage, networking"]),
                ("Module 2: Cloud Security", ["introduction to Microsoft Azure security and AWS security concepts", "cloud IAM, security groups", "cloud logging and monitoring", "cloud configuration security"]),
                ("Module 3: Identity Security", ["IAM, RBAC, privileged access, MFA", "conditional access, service accounts", "identity lifecycle", "Zero Trust"]),
                ("Module 4: Endpoint Security", ["EDR, antivirus", "endpoint monitoring, application control", "device management, endpoint hardening"]),
                ("Module 5: Security Architecture", ["defence in depth", "Zero Trust", "network segmentation", "secure architecture, security controls", "risk-based security"]),
                ("Module 6: Security Automation", ["using Python and scripting for log processing, IOC extraction, automated enrichment, alert processing, report generation, API integration"]),
            ],
            "capstone_title": "Enterprise Security Architecture & Automation",
            "capstone_desc": "Learners design a secure environment for a fictional organisation covering employees, servers, endpoints, cloud resources, applications, databases, and remote workers, including network architecture, IAM, MFA, firewall, EDR, SIEM, vulnerability management, backup, incident response, and security monitoring, plus a Python security automation tool that collects, analyses, enriches, alerts, and reports.",
        },
        {
            "title": "Month 7: Advanced Cyber Defence & Threat Intelligence",
            "objective": "This becomes the final graduation project, bringing the entire programme together into a realistic enterprise cyber-defence operation.",
            "modules": [
                ("Module 1: Advanced Threat Hunting", ["threat hunting methodology, hypothesis-driven hunting", "IOC, behavioural, endpoint, network, and identity hunting"]),
                ("Module 2: Advanced Detection", ["detection engineering", "Sigma rules, YARA fundamentals", "SIEM queries, correlation rules", "detection validation"]),
                ("Module 3: Threat Intelligence Operations", ["intelligence requirements, collection, processing, analysis, dissemination", "the intelligence lifecycle", "STIX/TAXII, IOC management, threat reports"]),
                ("Module 4: Security Automation", ["Python-based IOC extraction, threat feed ingestion, API integration", "log analysis, automated enrichment, alert generation, security reporting"]),
                ("Module 5: Security Governance", ["risk management, security policies, asset management", "business continuity, disaster recovery", "security awareness, compliance concepts"]),
            ],
            "capstone_title": "Enterprise Cyber Defence & Threat Intelligence Platform",
            "capstone_desc": "The programme's flagship project: learners create an integrated security operations environment for a fictional organisation: asset monitoring, SIEM, threat intelligence (import/enrich IOCs, track threats, map TTPs), threat hunting, incident response, Python-based security automation, and reporting (SOC, incident, threat intelligence, vulnerability, and executive security reports).",
        },
    ],
}


# =============================================================================
# PROGRAMME 3: Data Analytics Professional Programme (7 months)
# =============================================================================
DATA_ANALYTICS = {
    "dept_code": "DAI",
    "code": "DAP",
    "name": "Data Analytics Professional Programme",
    "tagline": "Learn to transform raw data into meaningful insights, interactive dashboards, and data-driven decisions.",
    "overview": (
        "Takes a learner from little or no data analytics experience through to the "
        "ability to work on realistic business datasets, perform analysis, build "
        "dashboards, communicate insights, and develop a professional data "
        "portfolio, using Excel, SQL, Python, Pandas, Power BI, and statistics."
    ),
    "description": (
        "The Data Analytics Professional Programme progresses through three stages: "
        "Beginner (Months 1-2, data fundamentals, Excel, and statistics), "
        "Intermediate (Months 3-4, SQL, Python, data cleaning, visualisation, and "
        "the first major project), and Advanced (Months 5-7, Power BI, advanced "
        "analytics, automation, predictive analytics, and business intelligence).\n\n"
        "The programme stays centred on a coherent Excel + SQL + Python + Power BI "
        "toolset, and finishes with an enterprise-level analytics capstone that "
        "brings all four together into one business intelligence platform."
    ),
    "career_paths": [
        "Data Analyst", "Junior Data Analyst", "Business Intelligence Analyst",
        "Reporting Analyst", "Power BI Developer", "Business Analyst",
    ],
    "learning_outcomes": [
        "Data Analysis: data collection, cleaning, transformation, exploratory data analysis, statistical analysis, data interpretation",
        "Excel: advanced formulas, pivot tables, data cleaning, dashboards, reporting",
        "SQL: queries, joins, aggregations, CTEs, window functions, analytical SQL",
        "Python: Pandas, NumPy, data cleaning, EDA, visualisation, automation, APIs",
        "Power BI: Power Query, data modelling, DAX, interactive dashboards, KPI development, business intelligence",
        "Statistics: descriptive statistics, probability, correlation, regression, hypothesis testing, forecasting",
        "Business: requirements gathering, KPI development, data storytelling, executive reporting, insight communication, business decision support",
    ],
    "months": [
        {
            "title": "Month 1: Introduction to Data Analytics & Excel",
            "objective": "Build a strong understanding of data and teach learners how to use Excel to organise, analyse, and communicate information.",
            "modules": [
                ("Module 1: Introduction to Data Analytics", ["what is data", "structured vs unstructured, qualitative vs quantitative, primary vs secondary data", "data analytics vs data science, data analyst vs data scientist vs BI analyst", "the analytics lifecycle: business problem to data collection to preparation to analysis to visualisation to insights to business decision"]),
                ("Module 2: Excel Fundamentals", ["the Excel interface", "worksheets and workbooks", "rows and columns", "data entry and types", "formatting, sorting, filtering", "tables, named ranges"]),
                ("Module 3: Excel Formulas", ["SUM, AVERAGE, MIN, MAX, COUNT, COUNTA, IF, IFS, AND, OR", "lookup functions: XLOOKUP, VLOOKUP, HLOOKUP, INDEX, MATCH", "SUMIF(S), COUNTIF(S), AVERAGEIF(S)"]),
                ("Module 4: Data Cleaning with Excel", ["duplicate records", "missing values", "incorrect data types", "text cleaning, date formatting", "data validation, find and replace", "removing unwanted spaces, standardising categories"]),
                ("Module 5: Excel Visualisation", ["bar, line, pie, scatter, and combination charts", "conditional formatting", "sparklines", "basic dashboards"]),
                ("Module 6: Pivot Tables", ["creating pivot tables, grouping data", "calculated fields, pivot charts", "filters, slicers, interactive reports"]),
            ],
            "capstone_title": "Personal & Household Finance Analytics Dashboard",
            "capstone_desc": "Learners receive a raw financial dataset and must clean it, categorise transactions, calculate income and expenses, analyse spending patterns, identify major spending categories, calculate savings, build an Excel dashboard, and present three to five key insights.",
        },
        {
            "title": "Month 2: Statistics, Data Preparation & Visualisation",
            "objective": "Teach learners the statistical thinking required to interpret data correctly.",
            "modules": [
                ("Module 1: Descriptive Statistics", ["mean, median, mode, range", "variance, standard deviation", "percentiles, quartiles, interquartile range"]),
                ("Module 2: Data Distribution", ["normal distribution, skewness, outliers", "frequency distributions, histograms, box plots"]),
                ("Module 3: Probability Fundamentals", ["probability concepts and events", "probability distributions", "expected value", "basic conditional probability"]),
                ("Module 4: Correlation & Relationships", ["positive, negative, and no correlation", "correlation vs causation", "scatter plots, trend lines"]),
                ("Module 5: Data Quality", ["accuracy, completeness, consistency, validity, timeliness, uniqueness"]),
                ("Module 6: Data Preparation", ["introduction to ETL, data transformation, data integration", "data profiling, data validation"]),
                ("Module 7: Data Storytelling", ["finding patterns and identifying trends", "selecting appropriate charts", "communicating insights, executive summaries", "avoiding misleading visualisations"]),
            ],
            "capstone_title": "Customer Behaviour Analysis",
            "capstone_desc": "Learners analyse a customer dataset (demographics, purchases, products, locations, order frequency, customer value) and identify customer trends, the most valuable customer segments, purchasing patterns, product preferences, geographic patterns, and potential business opportunities.",
        },
        {
            "title": "Month 3: SQL & Database Analytics",
            "objective": "Teach learners to retrieve, transform, and analyse data directly from relational databases.",
            "modules": [
                ("Module 1: Database Fundamentals", ["relational databases, tables, records, fields", "primary and foreign keys, relationships", "normalisation"]),
                ("Module 2: SQL Fundamentals", ["SELECT, FROM, WHERE, ORDER BY, LIMIT, DISTINCT"]),
                ("Module 3: SQL Functions", ["aggregate functions: COUNT, SUM, AVG, MIN, MAX"]),
                ("Module 4: Filtering & Grouping", ["AND, OR, IN, BETWEEN, LIKE", "GROUP BY, HAVING"]),
                ("Module 5: SQL Joins", ["INNER, LEFT, RIGHT, and FULL joins", "self joins"]),
                ("Module 6: Advanced SQL", ["subqueries, Common Table Expressions", "CASE statements", "window functions, ranking, running totals", "date analysis"]),
                ("Module 7: Database Analytics", ["working with realistic databases containing customers, products, orders, employees, transactions, and locations"]),
            ],
            "capstone_title": "Retail Database Analytics",
            "capstone_desc": "Learners query a relational database to answer business questions: total sales, top revenue products, highest-value customers, best-performing regions, monthly sales trends, declining products, average order value, and deliver a SQL script, query documentation, an analytical report, visualisations, and business recommendations.",
        },
        {
            "title": "Month 4: Python for Data Analytics",
            "objective": "Teach learners to use Python for data manipulation, analysis, and visualisation. This is the beginning of the four-month major practical project phase.",
            "modules": [
                ("Module 1: Python Fundamentals for Analysts", ["variables, data types, lists, dictionaries", "functions, loops, conditions, modules", "exception handling"]),
                ("Module 2: NumPy", ["arrays, array operations, mathematical functions", "indexing, filtering, aggregation"]),
                ("Module 3: Pandas", ["Series and DataFrames", "importing and exporting data", "filtering, sorting, grouping, aggregation, merging, joining"]),
                ("Module 4: Data Cleaning with Python", ["missing values, duplicates, incorrect formats, outliers", "data type conversion, string cleaning, date processing"]),
                ("Module 5: Data Visualisation", ["using Matplotlib and/or Plotly for bar, line, histogram, scatter, box, and heatmap charts", "interactive visualisations"]),
                ("Module 6: Exploratory Data Analysis", ["asking analytical questions", "exploring distributions, identifying relationships and anomalies", "identifying trends, generating hypotheses"]),
            ],
            "capstone_title": "Sales & Customer Analytics Project",
            "capstone_desc": "Learners receive a multi-table business dataset (customers, products, orders, transactions, locations, marketing campaigns) and analyse sales/revenue/profit trends, customer segmentation/value/churn indicators, product performance, and regional performance, delivering a Jupyter Notebook, a clean dataset, SQL queries, an analytical report, visualisations, and an executive presentation.",
        },
        {
            "title": "Month 5: Power BI & Business Intelligence",
            "objective": "Transform analytical results into professional, interactive business intelligence dashboards.",
            "modules": [
                ("Module 1: Power BI Fundamentals", ["the Power BI ecosystem and Power BI Desktop", "data sources, importing data", "data modelling, reports, dashboards"]),
                ("Module 2: Power Query", ["data extraction, transformation, cleaning", "merging, appending", "data types, query parameters"]),
                ("Module 3: Data Modelling", ["fact and dimension tables", "star schema, relationships, cardinality", "date tables"]),
                ("Module 4: DAX", ["fundamentals, measures, calculated columns and tables", "CALCULATE, SUM, AVERAGE, COUNT, DISTINCTCOUNT, FILTER, ALL", "time intelligence functions"]),
                ("Module 5: Dashboard Design", ["KPI cards, tables, charts, slicers", "drill-down, drill-through, tooltips", "bookmarks, navigation"]),
                ("Module 6: Business Intelligence", ["KPI development, performance analysis", "management, executive, and operational reporting"]),
            ],
            "capstone_title": "Business Intelligence Dashboard",
            "capstone_desc": "Learners build an interactive Power BI solution for a fictional organisation with Executive Overview, Sales Analysis, Customer Analysis, and Product Analysis pages, delivering a Power BI .pbix file, a data model, DAX measures, a dashboard, a data dictionary, and an executive report.",
        },
        {
            "title": "Month 6: Advanced Analytics, Forecasting & Automation",
            "objective": "Move beyond descriptive analytics into predictive and automated analytics.",
            "modules": [
                ("Module 1: Advanced Statistics", ["sampling, confidence intervals", "hypothesis testing, p-values, statistical significance", "A/B testing, regression fundamentals"]),
                ("Module 2: Predictive Analytics", ["predictive analytics concepts: regression, classification, time-series fundamentals", "model evaluation, train/test datasets"]),
                ("Module 3: Forecasting", ["time-series data, trends, seasonality, moving averages", "forecasting models, forecast evaluation"]),
                ("Module 4: Machine Learning for Analysts", ["introduction to Scikit-learn: linear regression, logistic regression, decision trees, random forests, clustering (used appropriately for analytics, not to turn this into a full data-science programme)"]),
                ("Module 5: Data Automation", ["using Python for automated data collection, cleaning, and reporting", "scheduled analysis, API data collection, Excel report generation"]),
                ("Module 6: APIs & Data Sources", ["REST APIs, JSON, API authentication", "extracting data, working with external datasets"]),
            ],
            "capstone_title": "Business Forecasting & Predictive Analytics Project",
            "capstone_desc": "A retail company wants to understand future sales and identify factors associated with customer churn. Learners collect, clean, and explore historical data, analyse relationships, build and evaluate a predictive model, produce forecasts, visualise results, explain limitations, and present business insights, delivering a Python notebook, statistical analysis, a forecasting model, visualisations, a Power BI dashboard, and an executive presentation.",
        },
        {
            "title": "Month 7: Enterprise Data Analytics & BI",
            "objective": "This is the final graduation project, bringing Excel, SQL, Python, statistics, Power BI, data engineering concepts, and business intelligence together into one enterprise-level analytics project.",
            "modules": [
                ("Module 1: Enterprise Analytics", ["data analytics strategy", "data governance, data ownership, data quality", "data catalogues, data lineage"]),
                ("Module 2: Data Warehousing Fundamentals", ["OLTP vs OLAP", "data warehouses, data marts", "ETL/ELT, star schema, fact and dimension tables"]),
                ("Module 3: Advanced Power BI", ["advanced DAX, time intelligence, dynamic measures", "advanced filtering, performance optimisation", "dashboard UX, row-level security"]),
                ("Module 4: Advanced SQL", ["CTEs, window functions, query optimisation", "complex joins, analytical queries", "views, stored procedures introduction"]),
                ("Module 5: Python Analytics Automation", ["automated ETL, API integration, data pipelines", "scheduled analytics, automated reports, database integration"]),
                ("Module 6: Professional Data Analytics", ["requirements gathering, stakeholder interviews", "KPI definition, data storytelling", "executive presentations, business reporting", "communicating uncertainty, writing analytical recommendations"]),
            ],
            "capstone_title": "Enterprise Business Intelligence & Analytics Platform",
            "capstone_desc": "Learners work as a professional analytics team supporting a fictional organisation with multiple data sources (CRM, sales system, inventory, marketing), building a pipeline through SQL and Python analytics into a data warehouse and Power BI executive dashboard covering sales, customer, marketing, and inventory analytics plus sales forecasting and churn indicators. Each learner/team presents the project as though presenting to a company's management team.",
        },
    ],
}


# =============================================================================
# PROGRAMME 4: Mobile App Development Using React Native (8 months)
# =============================================================================
MOBILE_APP_DEV = {
    "dept_code": "SWD",
    "code": "MAD",
    "name": "Mobile App Development Using React Native",
    "tagline": "Build production-ready, cross-platform mobile apps with React Native, from JavaScript fundamentals to the App Store.",
    "overview": (
        "Takes learners from programming fundamentals to the development, testing, "
        "deployment, and maintenance of production-ready mobile applications. "
        "Learners build cross-platform apps for Android and iOS using React Native "
        "while developing strong foundations in JavaScript, TypeScript, React, "
        "APIs, databases, authentication, mobile security, cloud services, "
        "testing, performance optimisation, and app deployment. The programme "
        "emphasises learning by building, with progressively complex projects "
        "leading to a final production-grade mobile application."
    ),
    "description": (
        "The Mobile App Development Using React Native Professional Programme "
        "progresses through three stages: Beginner (Months 1-2, programming and "
        "mobile development foundations), Intermediate (Months 3-5, professional "
        "React Native development), and Advanced (Months 6-8, production, "
        "security, and deployment).\n\n"
        "Core technology stack: JavaScript, TypeScript, React, React Native, Expo, "
        "React Navigation, Redux Toolkit, REST APIs, Node.js, Django/DRF, JWT, "
        "Firebase, PostgreSQL/MySQL, Jest, and CI/CD via GitHub Actions and Expo "
        "Application Services."
    ),
    "career_paths": [
        "React Native Developer", "Mobile App Developer", "Junior Mobile Software Engineer",
        "React Developer", "Front-End Developer", "Cross-Platform App Developer",
        "Full-Stack Mobile Developer", "Mobile Application Tester",
        "Mobile Application Support Developer", "Software Developer",
    ],
    "learning_outcomes": [
        "Develop mobile applications using React Native.",
        "Write professional JavaScript and TypeScript.",
        "Build reusable React Native components and design responsive mobile interfaces.",
        "Develop Android and iOS applications from a shared codebase.",
        "Integrate REST APIs and backend systems, and implement authentication and authorization.",
        "Work with databases and cloud services, including Firebase.",
        "Implement notifications, location, camera, and other device capabilities.",
        "Build real-time mobile applications and apply mobile application security principles.",
        "Test and debug mobile applications, and optimise application performance.",
        "Implement state management using modern React technologies (Context API, Redux Toolkit).",
        "Configure CI/CD workflows, and build and release production applications.",
        "Publish applications to Google Play and the Apple App Store, and build a professional mobile development portfolio.",
    ],
    "months": [
        {
            "title": "Month 1: JavaScript Programming Fundamentals",
            "objective": "Introduction to software and mobile application development, and establish strong JavaScript foundations.",
            "modules": [
                ("Module 1: JavaScript Syntax & Fundamentals", ["programming concepts and problem solving", "variables, constants, and data types", "operators and expressions", "conditional statements, loops and iteration", "functions", "arrays and objects", "string and number manipulation", "error handling"]),
                ("Module 2: ES6+ JavaScript", ["arrow functions", "destructuring", "spread/rest operators", "modules", "introduction to asynchronous JavaScript: promises and async/await"]),
                ("Module 3: Tooling", ["introduction to Git and GitHub", "programming exercises and JavaScript mini applications"]),
            ],
            "capstone_title": "Personal Productivity App",
            "capstone_desc": "Learners build a command-line/browser-based productivity application that demonstrates JavaScript programming fundamentals.",
        },
        {
            "title": "Month 2: React Fundamentals & Mobile Development",
            "objective": "Introduce React and React Native, and build the first mobile interfaces.",
            "modules": [
                ("Module 1: Introduction to React", ["React architecture, components, JSX, props, state, events", "conditional rendering, lists and keys, forms and validation", "React Hooks: useState, useEffect, component lifecycle concepts, reusable components"]),
                ("Module 2: Introduction to React Native", ["React Native architecture", "Expo and React Native CLI", "Android and iOS development environments", "mobile layouts: View, Text, Image, ScrollView, TextInput, Button, Pressable", "styling and Flexbox, responsive mobile interfaces"]),
            ],
            "capstone_title": "Mobile To-Do & Task Management App",
            "capstone_desc": "A functional mobile task-management application with task creation, editing and deletion, categories, task completion, search/filter, a responsive UI, and local data storage.",
        },
        {
            "title": "Month 3: React Native Application Development",
            "objective": "Develop professional React Native applications with navigation, forms, and reusable components.",
            "modules": [
                ("Module 1: Navigation & Screen Management", ["React Native project structure", "stack, tab, drawer, and nested navigation, navigation parameters"]),
                ("Module 2: Forms & Storage", ["form validation, keyboard management", "local storage with AsyncStorage", "device capabilities and permissions"]),
                ("Module 3: Lists, Media & UI", ["images and media, FlatList and SectionList", "pull-to-refresh, loading and error states", "reusable UI components, mobile UI/UX principles"]),
            ],
            "capstone_title": "Expense & Personal Finance Mobile App",
            "capstone_desc": "A mobile app with a user dashboard, income and expense categories, transaction history, search and filtering, monthly summaries with charts, local persistence, and a responsive mobile interface.",
        },
        {
            "title": "Month 4: APIs, Backend Integration & Authentication",
            "objective": "Connect React Native applications to backend systems and implement secure authentication.",
            "modules": [
                ("Module 1: REST APIs", ["understanding REST APIs, HTTP and HTTPS", "GET, POST, PUT, PATCH, DELETE, JSON", "Fetch API, Axios, API service architecture"]),
                ("Module 2: Authentication", ["registration, login/logout, password security", "token-based authentication, JWT, refresh tokens", "secure authentication flows, protected screens, role-based access"]),
                ("Module 3: Integration", ["API error handling, environment variables", "backend integration using Node.js/Django APIs"]),
            ],
            "capstone_title": "Mobile Business Management Application",
            "capstone_desc": "A mobile application connected to a backend API, with possible features including user registration, login, a dashboard, customer management, products/services, orders, sales, search, notifications, and profile management with API-based data storage.",
        },
        {
            "title": "Month 5: Databases, Cloud Services & Advanced Mobile Features",
            "objective": "Integrate cloud services, offline data, and device-level capabilities into mobile applications.",
            "modules": [
                ("Module 1: Mobile Data Architecture", ["SQL and NoSQL concepts", "Firebase fundamentals, Cloud Firestore, authentication services, cloud storage"]),
                ("Module 2: Real-Time & Offline", ["real-time data, push notifications, Firebase Cloud Messaging", "offline-first application concepts, data synchronisation"]),
                ("Module 3: Device Capabilities", ["image/file uploads, camera integration", "location services, maps, geolocation", "deep linking, QR/barcode scanning, device permissions, background tasks"]),
            ],
            "capstone_title": "Service Booking Mobile Application",
            "capstone_desc": "A service-booking application supporting customer accounts, service discovery, provider profiles, booking, a calendar, location, notifications, image uploads, booking status, and customer/provider dashboards.",
        },
        {
            "title": "Month 6: Mobile Security, Testing & Performance",
            "objective": "Secure, test, and optimise a mobile application to production standard.",
            "modules": [
                ("Module 1: Secure Mobile Application Development", ["OWASP Mobile Application Security", "secure authentication, token protection, secure API communication", "input validation, secure local storage, secrets management, data encryption concepts", "application permissions, authentication vulnerabilities, API security, secure file uploads, mobile threat modelling"]),
                ("Module 2: Testing", ["React Native testing: unit, component, integration, and end-to-end testing", "Jest, React Native Testing Library", "error monitoring, debugging"]),
                ("Module 3: Performance", ["performance optimisation, memory management", "application startup performance, network optimisation"]),
            ],
            "capstone_title": "Secure Mobile Application",
            "capstone_desc": "Learners take an existing mobile application and perform a security assessment, authentication hardening, API security improvements, input validation, secure storage implementation, automated testing, performance optimisation, and error monitoring.",
        },
        {
            "title": "Month 7: Advanced React Native & Production Architecture",
            "objective": "Apply advanced React patterns, state management, and real-time features at production scale.",
            "modules": [
                ("Module 1: Advanced React Patterns", ["TypeScript with React Native: strong typing, interfaces and types, generic components", "state management: Context API, Redux Toolkit, advanced and custom hooks"]),
                ("Module 2: Application Architecture", ["feature-based architecture, clean code principles, design patterns, dependency management", "API caching, offline applications"]),
                ("Module 3: Real-Time & Production Readiness", ["real-time communication: WebSockets, chat functionality, advanced notifications", "payment integration concepts, analytics, crash reporting", "CI/CD fundamentals: GitHub Actions, build automation"]),
            ],
            "capstone_title": "Real-Time Mobile Platform",
            "capstone_desc": "A production-style application with authentication, user profiles, real-time communication, push notifications, API integration, search, file/image sharing, state management, offline support, analytics, and secure data handling.",
        },
        {
            "title": "Month 8: App Deployment, DevOps & Final Professional Project",
            "objective": "Prepare, deploy, and maintain mobile applications in production, and complete the final capstone.",
            "modules": [
                ("Module 1: Preparing for Production", ["Android and iOS application lifecycle", "Android APK/AAB, iOS builds, Expo Application Services (EAS)", "app signing, certificates, provisioning profiles", "application and environment configuration"]),
                ("Module 2: Deployment & Monitoring", ["production APIs, database deployment, cloud deployment", "CI/CD pipelines, version control and release management, semantic versioning", "application performance monitoring, crash monitoring"]),
                ("Module 3: Store Submission & Portfolio", ["App Store and Google Play requirements and submission", "application privacy, terms and conditions", "production maintenance, updates and version releases", "mobile application portfolio development, technical documentation, CV/GitHub/portfolio development, interview preparation"]),
            ],
            "capstone_title": "Production-Ready Mobile Application",
            "capstone_desc": "The final capstone: learners design, develop, test, and deploy a complete real-world mobile application (e.g. healthcare, e-commerce, food delivery, LMS, hotel booking, property management, pharmacy, business/POS, social networking, financial management, or logistics), demonstrating professional UI/UX, authentication and authorisation, REST API integration, database integration, state management, push notifications, file/image handling, secure data management, error handling, automated testing, performance optimisation, analytics/monitoring, production deployment, and technical documentation.",
        },
    ],
}


# =============================================================================
# PROGRAMME 5: AI & Machine Learning Using Python (8 months)
# =============================================================================
AI_MACHINE_LEARNING = {
    "dept_code": "DAI",
    "code": "AIM",
    "name": "AI & Machine Learning Using Python",
    "tagline": "From Python fundamentals to deployed AI systems: machine learning, deep learning, and generative AI, built practically.",
    "overview": (
        "Takes learners from foundational Python and data skills to the "
        "development, evaluation, deployment, and maintenance of real-world "
        "artificial intelligence and machine learning solutions, following a "
        "learn, experiment, build, evaluate, deploy approach with "
        "progressively more advanced projects leading to a final AI solution."
    ),
    "description": (
        "The AI & Machine Learning Using Python Professional Programme progresses "
        "through three stages: Beginner (Months 1-2, Python, data, and AI "
        "foundations), Intermediate (Months 3-5, machine learning and applied "
        "AI), and Advanced (Months 6-8, deep learning, generative AI, and "
        "production AI).\n\n"
        "Core technologies: NumPy, Pandas, Matplotlib, Seaborn, Scikit-learn, "
        "TensorFlow/PyTorch, Hugging Face, vector databases, FastAPI/Django, and "
        "Docker/CI-CD for MLOps."
    ),
    "career_paths": [
        "Junior Machine Learning Engineer", "AI Developer", "Machine Learning Developer",
        "AI/ML Engineer", "Python Developer", "Data Analyst", "Junior Data Scientist",
        "Machine Learning Analyst", "AI Application Developer", "NLP Developer",
        "Computer Vision Developer", "Generative AI Developer", "AI Automation Developer",
        "MLOps Engineer", "AI Solutions Developer",
    ],
    "learning_outcomes": [
        "Develop AI and ML applications using Python.",
        "Analyse and prepare datasets for machine learning, and apply statistical and mathematical concepts to AI problems.",
        "Build supervised and unsupervised machine learning models, engineer and select useful features, and evaluate and compare models.",
        "Build predictive analytics solutions, recommendation systems, and anomaly detection using machine learning.",
        "Build neural networks and deep-learning models, including computer vision applications.",
        "Build NLP applications, integrate Large Language Models, and build RAG-based AI assistants.",
        "Develop AI APIs using FastAPI or Django, and apply AI security, privacy, and responsible-AI principles.",
        "Containerise and deploy AI applications, understand MLOps, and monitor and maintain deployed models.",
        "Build a professional AI/ML portfolio.",
    ],
    "months": [
        {
            "title": "Month 1: Python Programming for AI",
            "objective": "Introduce Artificial Intelligence and Machine Learning, and establish a strong Python foundation for AI work.",
            "modules": [
                ("Module 1: AI & ML Foundations", ["introduction to Artificial Intelligence and Machine Learning", "AI vs Machine Learning vs Deep Learning", "real-world applications of AI"]),
                ("Module 2: Python for AI", ["Python development environment", "variables, data types, operators, conditionals, loops, functions", "lists, tuples, sets, dictionaries, strings and data manipulation", "list/dictionary comprehensions, modules and packages, exception handling, file handling"]),
                ("Module 3: Professional Tooling", ["object-oriented programming fundamentals", "virtual environments, package management with pip", "Jupyter Notebook, Git and GitHub", "introduction to NumPy"]),
            ],
            "capstone_title": "AI Personal Assistant (Python Prototype)",
            "capstone_desc": "Learners create a Python-based assistant capable of processing user input and performing predefined tasks such as calculations, information retrieval, and simple automation.",
        },
        {
            "title": "Month 2: Mathematics, Statistics & Data Analysis for AI",
            "objective": "Build the mathematical and statistical foundations required for machine learning, and practise data analysis in Python.",
            "modules": [
                ("Module 1: Mathematics for Machine Learning", ["variables and functions, linear algebra fundamentals", "vectors and matrices, matrix operations"]),
                ("Module 2: Probability & Statistics", ["introduction to probability, probability distributions", "mean, median, mode, variance, standard deviation, correlation and covariance", "descriptive statistics, inferential statistics fundamentals, data types and data quality"]),
                ("Module 3: NumPy, Pandas & EDA", ["NumPy, Pandas, DataFrames and Series", "data cleaning: missing values, duplicate records, outlier detection, data transformation", "Matplotlib, Seaborn, exploratory data analysis (EDA)"]),
            ],
            "capstone_title": "Business Data Intelligence & EDA Project",
            "capstone_desc": "Learners analyse a real-world dataset, clean the data, identify patterns and trends, create visualisations, and produce an analytical report explaining their findings.",
        },
        {
            "title": "Month 3: Machine Learning Fundamentals",
            "objective": "Introduce supervised and unsupervised machine learning and the standard model training workflow.",
            "modules": [
                ("Module 1: Introduction to Machine Learning", ["supervised, unsupervised, and semi-supervised learning", "reinforcement learning introduction", "features and target variables, training and testing datasets"]),
                ("Module 2: Preprocessing", ["data preprocessing, feature scaling, encoding categorical variables", "train/validation/test splits, cross-validation"]),
                ("Module 3: Regression & Classification", ["linear, multiple, and polynomial regression", "logistic regression, K-Nearest Neighbours, decision trees, random forests", "model training and evaluation, overfitting and underfitting, bias and variance, Scikit-learn"]),
            ],
            "capstone_title": "Customer Churn Prediction System",
            "capstone_desc": "Learners develop a machine learning system that predicts whether a customer is likely to leave a service, including data preprocessing, feature engineering, model training, model comparison, evaluation, prediction, visualisation, and business recommendations.",
        },
        {
            "title": "Month 4: Advanced Machine Learning & Predictive Analytics",
            "objective": "Apply advanced modelling techniques, tuning, and evaluation to real predictive business problems.",
            "modules": [
                ("Module 1: Advanced Models", ["advanced regression and classification, Support Vector Machines", "Random Forest, Gradient Boosting, XGBoost fundamentals, ensemble learning"]),
                ("Module 2: Tuning & Feature Engineering", ["hyperparameter tuning: Grid Search, Random Search, cross-validation", "feature selection and engineering, dimensionality reduction, Principal Component Analysis (PCA)"]),
                ("Module 3: Evaluation", ["model interpretability, feature importance", "confusion matrix, precision, recall, F1-score, ROC-AUC, regression metrics", "model selection, imbalanced datasets, data leakage, machine learning pipelines"]),
            ],
            "capstone_title": "Predictive Business Analytics Platform",
            "capstone_desc": "Learners build a predictive system forecasting or classifying a business problem such as sales prediction, customer churn, credit-risk classification, demand forecasting, fraud detection, or property price prediction, comparing multiple models and justifying the final model based on documented evaluation metrics.",
        },
        {
            "title": "Month 5: Unsupervised Learning, Recommendation Systems & AI Applications",
            "objective": "Apply unsupervised learning and build recommendation and forecasting systems.",
            "modules": [
                ("Module 1: Unsupervised Machine Learning", ["clustering: K-Means, hierarchical clustering, DBSCAN, cluster evaluation", "dimensionality reduction (PCA), anomaly detection, association rules"]),
                ("Module 2: Recommendation Systems", ["collaborative filtering, content-based recommendations", "similarity measures, search and ranking concepts"]),
                ("Module 3: Time-Series & Automation", ["time-series fundamentals: trend and seasonality, forecasting fundamentals", "AI automation, model pipelines"]),
            ],
            "capstone_title": "AI Recommendation & Customer Intelligence System",
            "capstone_desc": "Learners build an AI system that analyses customer behaviour and generates personalised recommendations, with possible applications in product, food, course, property, or content recommendation, or customer segmentation.",
        },
        {
            "title": "Month 6: Deep Learning with Python",
            "objective": "Introduce neural networks and deep learning, and build a computer vision application.",
            "modules": [
                ("Module 1: Neural Network Fundamentals", ["biological vs artificial neurons, perceptrons, neural network architecture", "activation functions, forward propagation, backpropagation, loss functions"]),
                ("Module 2: Training & Optimisation", ["optimisation, gradient descent, learning rates, epochs and batches", "regularisation, dropout, batch normalisation"]),
                ("Module 3: Frameworks & CNNs", ["TensorFlow fundamentals, Keras, PyTorch introduction", "Convolutional Neural Networks, image classification, transfer learning", "model evaluation, GPU acceleration"]),
            ],
            "capstone_title": "AI Image Classification System",
            "capstone_desc": "Learners develop a deep-learning application capable of classifying images (e.g. medical images, animals, products, plant disease, documents, or general object recognition), including model training, validation, testing, and an application interface for making predictions.",
        },
        {
            "title": "Month 7: Natural Language Processing, Generative AI & Large Language Models",
            "objective": "Apply NLP and generative AI techniques, and build a retrieval-augmented AI assistant.",
            "modules": [
                ("Module 1: NLP Fundamentals", ["text preprocessing: tokenisation, stop words, stemming and lemmatisation", "Bag-of-Words, TF-IDF, text classification, sentiment analysis, Named Entity Recognition"]),
                ("Module 2: Transformers & LLMs", ["word embeddings, transformers, attention mechanisms", "Large Language Models, generative AI fundamentals, prompt engineering, AI APIs, open-source models, the Hugging Face ecosystem"]),
                ("Module 3: RAG & Responsible AI", ["embeddings, vector databases, semantic search, Retrieval-Augmented Generation (RAG)", "AI chatbots, AI agents fundamentals", "responsible AI, hallucination and model limitations, AI evaluation"]),
            ],
            "capstone_title": "AI Knowledge Assistant / RAG Chatbot",
            "capstone_desc": "Learners develop an intelligent chatbot that answers questions from a defined knowledge base, demonstrating document ingestion, text processing, embeddings, vector search, retrieval, LLM integration, context-aware responses, conversation history, source/reference retrieval, and basic safety controls, for example a university, healthcare, business-support, cybersecurity, or customer-service assistant.",
        },
        {
            "title": "Month 8: AI Engineering, Model Deployment & MLOps",
            "objective": "Deploy, monitor, and govern AI systems in production, and complete the final capstone.",
            "modules": [
                ("Module 1: AI System Architecture", ["the machine learning project lifecycle, AI system architecture", "model packaging, model serialisation, REST APIs for AI models: FastAPI, Django AI integration"]),
                ("Module 2: Deployment & Monitoring", ["Docker fundamentals, Git/GitHub, CI/CD for AI applications, cloud deployment concepts", "model serving, batch vs real-time inference", "model monitoring, data drift, model drift, model versioning, experiment tracking, ML pipelines, MLOps fundamentals"]),
                ("Module 3: Responsible & Scalable AI", ["logging and monitoring, AI security, privacy and data protection", "responsible AI, bias and fairness, AI governance", "cost optimisation, scaling AI applications", "technical documentation, AI portfolio development, production deployment"]),
            ],
            "capstone_title": "Production AI & Machine Learning Platform",
            "capstone_desc": "The final capstone: learners design and develop a complete AI-powered application solving a genuine business or societal problem, for example an AI healthcare, education, cybersecurity, business intelligence, or food intelligence platform, demonstrating data acquisition, cleaning, and exploratory analysis, machine learning/deep learning, model evaluation, AI integration, API development, database integration, a user interface, authentication/security, model deployment, monitoring, documentation, and Git/GitHub version control.",
        },
    ],
}


# =============================================================================
# PROGRAMME 6: Cybersecurity Governance, Risk & Compliance (GRC) (8 months)
# =============================================================================
CYBERSECURITY_GRC = {
    "dept_code": "CYB",
    "code": "CGR",
    "name": "Cybersecurity Governance, Risk & Compliance",
    "tagline": "Govern risk, manage compliance, and lead cybersecurity assurance: ISO 27001, NIST, GDPR, and enterprise GRC in practice.",
    "overview": (
        "Prepares learners for professional roles focused on managing "
        "cybersecurity risk, developing security governance structures, "
        "implementing policies and controls, supporting compliance requirements, "
        "conducting risk assessments, and preparing organisations for audits. "
        "Rather than focusing primarily on technical security operations, the "
        "programme develops the ability to identify, assess, manage, document, "
        "monitor, and communicate cybersecurity risks across an organisation, "
        "complementing, rather than duplicating, the SOC/technical focus of the "
        "Cybersecurity Analyst programme."
    ),
    "description": (
        "The Cybersecurity Governance, Risk & Compliance Professional Programme "
        "progresses through three stages: Beginner (Months 1-2, GRC foundations), "
        "Intermediate (Months 3-5, compliance, controls, and audit), and Advanced "
        "(Months 6-8, enterprise GRC and strategic cybersecurity).\n\n"
        "Learners work with widely used cybersecurity and governance frameworks "
        "including ISO/IEC 27001 and 27002, the NIST Cybersecurity Framework and "
        "Risk Management Framework, CIS Controls, COBIT, GDPR, and UK data "
        "protection principles, progressively developing policies, risk "
        "registers, control matrices, audit evidence, compliance assessments, "
        "business continuity plans, and a complete organisational GRC programme."
    ),
    "career_paths": [
        "Cybersecurity GRC Analyst", "GRC Analyst", "Cybersecurity Risk Analyst",
        "IT Risk Analyst", "Information Security Analyst (GRC)", "Compliance Analyst",
        "Cybersecurity Compliance Analyst", "Information Security Officer",
        "Security Governance Analyst", "IT Governance Analyst", "Security Controls Analyst",
        "IT Auditor", "Cybersecurity Auditor", "Third-Party Risk Analyst",
        "Vendor Risk Analyst", "Privacy/GRC Analyst", "Security Assurance Analyst",
        "Cyber Risk Consultant", "GRC Consultant", "Information Security Manager",
    ],
    "learning_outcomes": [
        "Explain cybersecurity governance, risk, and compliance principles, and develop cybersecurity governance structures.",
        "Create and maintain cybersecurity policies, identify and assess cybersecurity risks, and develop enterprise cybersecurity risk registers.",
        "Design risk treatment plans, apply ISO 27001 principles, and conduct cybersecurity framework gap assessments.",
        "Develop security control matrices, perform control testing, collect and evaluate audit evidence, and conduct internal cybersecurity audits.",
        "Develop compliance programmes, apply data protection and privacy principles, and conduct privacy and DPIA assessments.",
        "Assess third-party and supplier cybersecurity risks, and develop vendor risk management programmes.",
        "Develop business continuity and cyber-resilience plans.",
        "Produce executive cybersecurity reports and dashboards, and develop cybersecurity KPIs and KRIs.",
        "Communicate cybersecurity risk to non-technical stakeholders, and develop enterprise GRC roadmaps.",
        "Support ISO 27001 readiness and audit activities, establish continuous compliance and assurance processes, and design an enterprise cybersecurity GRC programme.",
    ],
    "months": [
        {
            "title": "Month 1: Introduction to Cybersecurity GRC",
            "objective": "Introduce governance, risk, and compliance within cybersecurity, and establish foundational GRC documentation.",
            "modules": [
                ("Module 1: Governance & Structures", ["governance, risk, and compliance explained", "the role of GRC within cybersecurity, governance structures", "board and executive responsibilities, security leadership and accountability", "roles and responsibilities, security policies and procedures"]),
                ("Module 2: Information Security Fundamentals", ["information assets, data classification", "confidentiality, integrity, and availability, security principles", "threats, vulnerabilities, and risks: risk vs threat vs vulnerability, risk ownership, risk appetite, risk tolerance", "security objectives, security metrics and KPIs"]),
                ("Module 3: Frameworks & Ethics", ["introduction to ISO 27001, NIST CSF, CIS Controls, and COBIT", "professional ethics and confidentiality, GRC documentation"]),
            ],
            "capstone_title": "Cybersecurity Governance Foundation Project",
            "capstone_desc": "Learners design a basic governance structure for a fictional organisation, including a governance structure, security policies, roles and responsibilities, an asset inventory, a data classification scheme, and an initial risk register.",
        },
        {
            "title": "Month 2: Cybersecurity Risk Management",
            "objective": "Apply risk management principles to identify, assess, treat, and report cybersecurity risk.",
            "modules": [
                ("Module 1: Risk Principles", ["risk identification, assessment, analysis, evaluation, and treatment", "risk acceptance, avoidance, mitigation, transfer, and monitoring"]),
                ("Module 2: Risk Assessment", ["qualitative and quantitative risk assessment", "likelihood and impact, risk scoring, inherent and residual risk", "risk appetite and tolerance"]),
                ("Module 3: Risk Documentation & Reporting", ["risk treatment plans, risk registers, risk ownership, Key Risk Indicators (KRIs), risk reporting", "threat modelling fundamentals, business impact analysis, asset criticality, security control selection, risk documentation"]),
            ],
            "capstone_title": "Enterprise Cybersecurity Risk Assessment",
            "capstone_desc": "Learners conduct a complete cybersecurity risk assessment for a fictional organisation, delivering an asset register, threat register, vulnerability register, risk register, risk matrix, risk treatment plan, residual risk assessment, and executive risk report.",
        },
        {
            "title": "Month 3: Security Frameworks, Controls & ISO 27001",
            "objective": "Apply ISO 27001/27002 and other security frameworks to build a control environment and identify gaps.",
            "modules": [
                ("Module 1: ISO 27001 & ISMS", ["ISO/IEC 27001, ISO/IEC 27002, Information Security Management System (ISMS) principles", "context of the organisation, interested parties, leadership and commitment", "information security objectives, risk assessment and treatment, Statement of Applicability"]),
                ("Module 2: Security Controls", ["security controls: ownership, design, implementation, effectiveness", "evidence collection, documented information, continuous improvement"]),
                ("Module 3: Framework Mapping", ["NIST Cybersecurity Framework, CIS Controls", "framework mapping, control crosswalks, gap assessments"]),
            ],
            "capstone_title": "ISO 27001 Readiness & Gap Assessment",
            "capstone_desc": "Learners assess a fictional organisation against an ISO 27001-based ISMS, identifying existing controls, missing controls, control gaps, risk implications, required evidence, remediation actions, and implementation priorities.",
        },
        {
            "title": "Month 4: Cybersecurity Compliance & Privacy",
            "objective": "Apply data protection and privacy principles, and manage cybersecurity compliance obligations.",
            "modules": [
                ("Module 1: Compliance Principles", ["cybersecurity compliance principles, regulatory vs contractual requirements", "data protection principles, GDPR fundamentals, UK data protection environment"]),
                ("Module 2: Data Protection", ["personal data, special-category data, data controllers and processors, data protection responsibilities", "data processing principles, lawful processing concepts, data subject rights, data retention, data minimisation, privacy by design"]),
                ("Module 3: Privacy Operations", ["Data Protection Impact Assessments (DPIAs), data breach management", "third-party data processing, international data transfers, records of processing activities, privacy policies", "compliance obligations register, regulatory monitoring, compliance evidence"]),
            ],
            "capstone_title": "GDPR & Cybersecurity Compliance Assessment",
            "capstone_desc": "Learners assess an organisation's handling of personal data and develop a remediation programme covering data protection, security controls, privacy, documentation, data retention, third-party processing, and incident/breach response.",
        },
        {
            "title": "Month 5: Internal Audit, Control Testing & Assurance",
            "objective": "Plan and conduct an internal cybersecurity audit, from evidence collection through to reporting.",
            "modules": [
                ("Module 1: Audit Planning", ["internal audit fundamentals, audit planning, scope, objectives, criteria, and programmes"]),
                ("Module 2: Evidence & Control Testing", ["audit evidence collection: interviews, document reviews, sampling", "control testing: design effectiveness, operating effectiveness, compliance testing"]),
                ("Module 3: Findings & Assurance", ["audit findings, non-conformities, observations, root cause analysis", "corrective actions, remediation tracking, audit reports, management responses, audit follow-up", "continuous assurance, GRC dashboards, security metrics"]),
            ],
            "capstone_title": "Cybersecurity Internal Audit Project",
            "capstone_desc": "Learners conduct a simulated internal cybersecurity audit, delivering an audit charter, scope, and plan, an audit checklist, control test procedures, an evidence register, findings, root-cause analysis, a corrective action plan, a final audit report, and an executive presentation.",
        },
        {
            "title": "Month 6: Third-Party Risk & Supply Chain Security",
            "objective": "Assess and manage cybersecurity risk introduced by vendors and the supply chain.",
            "modules": [
                ("Module 1: Vendor Risk Fundamentals", ["third-party cybersecurity risk, vendor risk management, supplier risk assessment, supply-chain cybersecurity", "vendor classification, critical suppliers, due diligence, security questionnaires, vendor security assessments"]),
                ("Module 2: Contractual & Ongoing Risk", ["contractual security requirements, service-level agreements, data processing agreements, security clauses, right-to-audit provisions", "vendor risk scoring, continuous vendor monitoring, third-party risk registers"]),
                ("Module 3: Cloud & Outsourcing Risk", ["cloud supplier risk, software supply-chain risk, outsourcing risk", "vendor incident management, supplier offboarding"]),
            ],
            "capstone_title": "Third-Party Cybersecurity Risk Management Programme",
            "capstone_desc": "Learners establish a complete vendor-risk management process for an organisation with multiple technology suppliers, delivering a vendor inventory, risk classification, a due-diligence questionnaire, a risk scoring model, contractual requirements, a remediation plan, a monitoring framework, and an executive vendor-risk report.",
        },
        {
            "title": "Month 7: Business Continuity, Incident Governance & Enterprise Resilience",
            "objective": "Develop business continuity, disaster recovery, and incident-governance capability for cyber resilience.",
            "modules": [
                ("Module 1: Business Continuity", ["business continuity management, cyber resilience, Business Impact Analysis", "critical business processes, recovery objectives (RTO, RPO), disaster recovery"]),
                ("Module 2: Incident Governance", ["business continuity plans, crisis management, incident response governance", "cyber incident escalation, incident classification, roles and responsibilities, crisis communications, regulatory notification considerations, lessons learned"]),
                ("Module 3: Resilience Testing", ["tabletop exercises, cyber resilience metrics, recovery planning", "backup governance, disaster recovery testing, operational resilience"]),
            ],
            "capstone_title": "Cyber Resilience & Business Continuity Programme",
            "capstone_desc": "Learners simulate a major cyber incident and develop a governance-led response covering incident, escalation, decision making, communication, recovery, and lessons learned, delivering an executive incident report and a resilience improvement plan.",
        },
        {
            "title": "Month 8: Enterprise GRC Strategy, Automation & Final Project",
            "objective": "Bring the entire programme together into a complete enterprise cybersecurity GRC programme for a realistic organisation. This is the final graduation project.",
            "modules": [
                ("Module 1: Enterprise GRC Architecture", ["GRC operating models, GRC maturity models, security governance structures", "enterprise risk management, security strategy, security roadmaps, cybersecurity budgets"]),
                ("Module 2: Executive Reporting & Automation", ["executive and board-level cybersecurity reporting, risk dashboards, security KPIs and KRIs, compliance dashboards, control monitoring", "GRC automation, GRC platforms, workflow automation, evidence management, continuous compliance, regulatory change management"]),
                ("Module 3: Programme Management & Tools", ["security awareness governance, cybersecurity programme management, GRC documentation, professional reporting, stakeholder management, communicating technical risk to executives, GRC career development", "exposure to GRC platforms and workflows such as ServiceNow GRC, RSA Archer, OneTrust, Microsoft Purview, Jira, Confluence, Excel, Power BI, and SharePoint"]),
            ],
            "capstone_title": "Enterprise Cybersecurity GRC Programme",
            "capstone_desc": "The programme's flagship project: learners design a complete GRC programme for a realistic organisation covering governance, risk management, compliance, security controls, audit, privacy, third-party risk, resilience, reporting, and a GRC roadmap from current to target maturity.",
        },
    ],
}


PROGRAMMES = [
    PYTHON_SOFTWARE_DEV,
    CYBERSECURITY_ANALYST,
    DATA_ANALYTICS,
    MOBILE_APP_DEV,
    AI_MACHINE_LEARNING,
    CYBERSECURITY_GRC,
]


class Command(BaseCommand):
    help = (
        "Seed the AbrayTech Academy Faculty/Department/Program/Course backend data "
        "for the 6 real training programmes described in the Website Content "
        "Development document."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        for programme_data in PROGRAMMES:
            self._seed_programme(programme_data)
        self.stdout.write(self.style.SUCCESS("\nAcademy courses seed complete."))

    def _seed_programme(self, data):
        department = get_or_create_department(data["dept_code"])
        months = data["months"]
        duration_years = round(len(months) / 12, 1)

        program, created = Program.objects.get_or_create(
            department=department, code=data["code"],
            defaults={"name": data["name"], "degree_level": "certificate", "duration_years": duration_years},
        )
        program.name = data["name"]
        program.degree_level = "certificate"
        program.duration_years = duration_years
        program.available_study_modes = ["Online", "Part Time"]
        program.tagline = data["tagline"]
        program.overview = data["overview"]
        program.description = data["description"]
        program.entry_requirements = ENTRY_REQUIREMENTS
        program.core_courses = [month["title"] for month in months]
        program.learning_outcomes = data["learning_outcomes"]
        program.career_paths = data["career_paths"]
        program.is_active = True
        program.save()

        for index, month in enumerate(months, start=1):
            course_code = f"{data['code']}{100 + index}"
            description = scheme_of_work(
                month["objective"], month["modules"],
                month["capstone_title"], month["capstone_desc"],
            )
            course, _ = Course.objects.get_or_create(
                program=program, code=course_code,
                defaults={"name": month["title"]},
            )
            course.name = month["title"]
            course.description = description
            course.is_active = True
            course.save()

        verb = "Created" if created else "Updated"
        self.stdout.write(
            f"{verb} Program {data['code']} ({data['name']}) with {len(months)} Course rows."
        )
