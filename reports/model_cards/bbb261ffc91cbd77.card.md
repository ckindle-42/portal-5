SYLink AI - Elite Cybersecurity AI 
 The First Cybersecurity-Specialized AI Model 

 Overview 

 Property 
 8B 
 32B 

 Developer 
 SYLink Technologie 
 SYLink Technologie 

 Parameters 
 8.2B 
 32.8B 

 Training Data 
 45,018 samples 
 63,313 samples 

 Context Length 
 32,768 tokens 
 16,384 tokens 

 Thinking Mode 
 Disabled 
 Enabled 

 License 
 Apache 2.0 
 Commercial 

 Model Selection 

 Model 
 Best For 
 Run Command 

 8B 
 Rapid triage, SOC Tier 1, resource-constrained environments 
 ollama run sylink/sylink:8b 

 32B 
 Deep analysis, incident investigation, compliance guidance, SOC Tier 2 ⁄ 3 
 ollama run sylink/sylink:32b 

 Capabilities 

 Threat Intelligence & Analysis 

 MITRE ATT&CK Framework mapping across all 14 tactics and 200+ techniques 
 Threat actor profiling (APT groups, ransomware operators, nation-state actors) 
 Indicators of Compromise (IOC) analysis and correlation 
 Zero-day and emerging threat assessment 

 Incident Response 

 Full IR lifecycle guidance (NIST CSF aligned) 
 Digital forensics support (memory, disk, network analysis) 
 Triage, containment, and eradication strategies 
 Evidence handling and chain of custody procedures 

 Vulnerability Management 

 CVE analysis with CVSS scoring interpretation 
 Risk-based patch prioritization 
 Attack surface management 
 Penetration testing methodology guidance 

 Compliance & Governance 

 Framework implementation (NIST 800-53, ISO 27001, CIS Controls) 
 SOC 2, PCI-DSS, HIPAA, GDPR compliance guidance 
 Risk assessment and policy development 
 Audit support and gap analysis 

 Detection Engineering 

 SIEM query optimization and correlation rules 
 Detection rule creation (Sigma, YARA, Snort/Suricata) 
 Threat hunting with hypothesis-driven approaches 
 Log analysis and anomaly detection 

 Usage 

 # 8B - Fast responses, lower resource usage
ollama run sylink/sylink:8b

# 32B - Deep analysis with thinking capability
ollama run sylink/sylink:32b

 Example Prompts 

 Threat Analysis: 

 Analyze this suspicious PowerShell command: powershell.exe -enc ZQBjAGgAbwAgACcAdABlAHMAdAAnAA==

 Incident Response: 

 We detected lateral movement from a compromised workstation. What containment steps should we take?

 Vulnerability Assessment: 

 How should we prioritize patching CVE-2024-3400 in our Palo Alto firewalls?

 Detection Engineering: 

 Write a Sigma rule to detect credential dumping via LSASS memory access

 Compliance: 

 What controls from NIST 800-53 address ransomware protection?

 Response Format 

 SYLink AI provides structured responses including: 

 MITRE ATT&CK Mapping : Technique IDs (Txxxx) when discussing attack patterns 
 Severity Ratings : Critical / High / Medium / Low classifications 
 Actionable Guidance : Specific, implementable recommendations 
 Detection Opportunities : IOCs and monitoring strategies 

 Parameters 

 8B Model 

 Parameter 
 Default 
 Description 

 temperature 
 0.6 
 Balanced for quick, accurate responses 

 top_p 
 0.9 
 Comprehensive coverage 

 top_k 
 40 
 Balance diversity and accuracy 

 num_ctx 
 32768 
 Extended context for security logs 

 num_predict 
 4096 
 Detailed response length 

 32B Model 

 Parameter 
 Default 
 Description 

 temperature 
 0.3 
 Lower for precise, thorough analysis 

 top_p 
 0.85 
 Focused coverage 

 top_k 
 40 
 Balance diversity and accuracy 

 num_ctx 
 16384 
 Context for detailed investigations 

 num_predict 
 8192 
 Extended response length 

 Ethical Guidelines 

 SYLink AI is designed for defensive cybersecurity only : 

 Provides guidance for protection, detection, and response 
 Declines requests for exploit development or malware creation 
 Advocates for responsible disclosure practices 
 Emphasizes legal compliance and authorized testing 
 Supports privacy-preserving security practices 

 Training 

 Trained on curated datasets of: 

 Incident response playbooks and case studies 
 MITRE ATT&CK technique documentation 
 Security advisory and CVE analysis 
 Compliance framework mappings 
 Threat intelligence reports 
 Detection rule repositories 

 Versions 

 Tag 
 Size 
 Quantization 
 Description 

 8b 
 16GB 
 F16 
 Fast triage, SOC Tier 1 

 32b 
 22GB 
 Q5_K_M 
 Deep analysis, thinking-capable 

 Links 

 Website : sylink.fr 
 Contact : contact@sylink.fr 

 License 

 8B : Apache 2.0 
 32B : Commercial License - SYLink Technologie 

 SYLink AI is developed by SYLink Technologie for enterprise cybersecurity operations.