## Problem
During Signal chat ingestion we only store comments; potential help requests buried in chats never become structured `HelpRequest` records unless an operator manually recreates them later.

## Option A – Auto-create requests inline during Signal import
- Pros: Immediate request creation with no operator effort; keeps chats and requests tightly linked; minimal additional UI.
- Cons: High risk of false positives/duplicates; hard to capture missing metadata (contact info, scope) synchronously; requires full guardrails before launch.

## Option B – LLM-powered “request candidate” queue with operator approval
- Pros: LLM can summarize candidate needs and pre-fill fields while humans confirm; reduces false positives; provides audit trail; lets us tune thresholds gradually.
- Cons: Adds review UI/workflow; requests are not live until someone approves; requires queue storage + assignment logic.

## Option C – Status quo (manual creation only)
- Pros: No new engineering; zero risk of incorrect auto-requests.
- Cons: Valuable requests stay hidden; heavy operator workload.

## Recommendation
Choose Option B. A candidate queue balances automation with safety: we can run the detector for every Signal message, store structured drafts (summary, tags, linked comments) in a staging table, and provide operators a lightweight approval UI that promotes a draft into an official `HelpRequest`. This keeps the ingestion pipeline simple, avoids spurious auto-posts, and still yields major time savings.
