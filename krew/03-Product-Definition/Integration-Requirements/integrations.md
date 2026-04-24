# Integration Requirements

## Tier 1: Must-Have at Launch
| System | Purpose | Examples |
|--------|---------|----------|
| **Slack** | Employee communication, Q&A, leave requests | Slack Bot API |
| **Google Workspace** | Calendar, email, docs | Google APIs |
| **Microsoft 365** | Calendar, email, Teams | Microsoft Graph API |
| **Email (SMTP)** | Notifications, offer letters, documents | SendGrid, AWS SES |

## Tier 2: Needed for Full Value (Months 3–9)
| System | Purpose | Examples |
|--------|---------|----------|
| **ATS** | Recruitment pipeline | Greenhouse, Lever, Ashby |
| **Payroll** | Payroll data sync | Gusto, ADP, Deel |
| **HRIS** | Employee data sync | BambooHR, Personio |
| **Document Signing** | Offer letters, contracts | DocuSign, PandaDoc |
| **Calendar** | Interview & meeting scheduling | Calendly, Cal.com |
| **Background Check** | Pre-employment screening | Checkr, Sterling |

## Tier 3: Nice-to-Have (Year 1+)
| System | Purpose | Examples |
|--------|---------|----------|
| **SSO/SAML** | Enterprise authentication | Okta, Azure AD |
| **LMS** | Learning content delivery | Udemy Business, Coursera |
| **Benefits** | Benefits enrollment | Sequoia, Justworks |
| **Accounting** | Expense and payroll sync | QuickBooks, Xero |
| **Ticketing** | HR case management | Jira, Zendesk |

## Integration Strategy
- Build a unified integration layer / middleware
- Prioritize bidirectional sync (not just read)
- Use OAuth 2.0 for all third-party connections
- Log all data syncs for audit trail
- Build generic CSV import/export as fallback

## Questions
- [ ] Build integrations in-house or use an iPaaS (Merge.dev, Finch)?
- [ ] Which ATS/HRIS to integrate with first? (Based on customer base)
