# QA Testing & Quality Assurance Skill

## Purpose
Comprehensive testing methodology to ensure code quality before deployment.
Never ship broken code. Always verify from user perspective.

---

## Core Principles

1. **Test immediately after writing code** - Don't wait, don't assume
2. **Test from user perspective** - If user can't use it, it doesn't work
3. **Use available data sources** - Check logs, BashOutput, endpoints
4. **Create observability** - Build monitoring infrastructure
5. **Proactive error detection** - Find problems before user does

---

## Testing Workflow (3 Levels)

### Level 1: Code Verification (5 minutes)
Run immediately after writing any code:

1. **Import Test**
   ```bash
   # Verify module can be imported
   python -c "from src.module.name import component"
   ```

2. **API Endpoint Test**
   ```bash
   # Test endpoint responds
   curl -s http://localhost:8100/api/your-endpoint
   ```

3. **Check BashOutput Logs**
   ```
   Use BashOutput tool to check running processes for errors
   Look for: ERROR, Exception, Traceback, Failed
   ```

**If ANY test fails → STOP and FIX before proceeding**

---

### Level 2: User Point of View Testing (10 minutes)
**CRITICAL:** Test EXACTLY how user experiences the feature

#### 2.1 User Environment Simulation
Put yourself in the user's shoes:
- Don't know internal implementation details
- Just want feature to work
- Expect clear feedback
- Need intuitive interface

#### 2.2 User Workflow Testing
**Step-by-step user journey:**

1. **Open User Interface**
   ```bash
   # For web interface
   Open: http://localhost:8100/dashboard.html
   # OR
   Open: http://13.61.17.19/dashboard.html (production)
   ```

2. **Open Browser Developer Tools**
   - Press F12 (Windows/Linux) or Cmd+Option+I (Mac)
   - Switch to Console tab
   - **Watch for red errors** (these are what user sees)
   - Keep Console open during entire test

3. **Perform User Action**
   - Click the button user would click
   - Fill the form user would fill
   - Navigate the path user would take
   - **Do NOT test via API** - test via actual UI

4. **Observe User Experience**
   - Does data appear? (user expects to see results)
   - Are there loading indicators? (user needs feedback)
   - Do buttons respond? (user expects immediate feedback)
   - Are error messages helpful? (user needs to understand what went wrong)

5. **Check Activity Log**
   ```bash
   # What does user see in activity log?
   curl http://localhost:8100/api/debug/activity-log | jq '.activities[-10:]'
   ```

#### 2.3 User Perspective Checklist

**For EVERY feature, verify:**

✅ **Visual Feedback**
- [ ] User sees confirmation when action succeeds
- [ ] User sees loading state during operations
- [ ] User sees helpful error messages on failure
- [ ] User can tell what's happening at all times

✅ **Functionality**
- [ ] Feature works on first try (not just after retries)
- [ ] Feature works with typical user data
- [ ] Feature handles edge cases gracefully
- [ ] Feature doesn't break other features

✅ **Browser Console (User's View)**
- [ ] Zero red errors in Console
- [ ] No repeated error messages
- [ ] No "404 Not Found" errors
- [ ] No "positions.filter is not a function" type errors

✅ **Activity Log (User's View)**
- [ ] Activity log shows feature working
- [ ] No error messages in activity stream
- [ ] Activities are in correct order
- [ ] Timestamps are recent

✅ **Network Tab (User's View)**
- [ ] All API calls return 200 (not 404 or 500)
- [ ] Response times < 1 second
- [ ] No failed requests shown in red
- [ ] Data format is correct

#### 2.4 User Acceptance Test

**The Ultimate Test:**
1. Close all browser tabs
2. Open fresh browser window
3. Go to dashboard as if you're the user
4. Try to use the feature WITHOUT looking at code
5. Can you successfully complete the task?

**If NO → Feature is NOT ready**
**If YES but saw errors → Feature is NOT ready**
**If YES and zero errors → Feature might be ready (proceed to Level 3)**

#### 2.5 Common User POV Mistakes

❌ **Testing via curl instead of browser**
- curl shows API works
- Doesn't show if UI is broken
- User uses UI, not curl

❌ **Not opening Developer Console**
- Console shows JavaScript errors
- These are what user experiences as "broken"
- Always check Console tab

❌ **Testing with developer knowledge**
- "I know to click here after clicking there"
- User doesn't know internal flow
- Test as if you don't know the code

❌ **Ignoring activity log errors**
- Activity log is what user sees
- Errors in activity log = bad user experience
- Always check activity log shows success

**If user can't use it → IT DOESN'T WORK**
**If user sees errors → IT DOESN'T WORK**
**If user is confused → IT DOESN'T WORK**

---

### Level 3: Integration Testing (30 minutes)
Before claiming "production ready":

1. **End-to-End Test**
   - Test complete user journey
   - Verify all components work together
   - Check database changes persist
   - Verify no side effects

2. **Error Handling Test**
   - Test with invalid inputs
   - Test with missing data
   - Test edge cases
   - Verify error messages are helpful

3. **Performance Test**
   - Check API response times
   - Verify no memory leaks
   - Check database query performance
   - Monitor resource usage

4. **Mode Switching Test** (if applicable)
   - Test in PAPER mode
   - Test in LIVE mode
   - Verify mode isolation
   - Check no cross-contamination

**If ANY test fails → DO NOT DEPLOY**

---

## Data Sources to Check

### Always Check These Before Claiming Complete:

1. **BashOutput from Running Processes**
   ```
   Check stderr and stdout for:
   - Error messages
   - Exceptions
   - Warnings
   - Failed operations
   ```

2. **Debug Endpoints**
   ```bash
   GET /api/debug/recent-errors
   GET /api/debug/activity-log
   GET /api/debug/error-summary
   ```

3. **Server Logs**
   ```bash
   # AWS
   ssh -i Main.pem ubuntu@13.61.17.19 "tail -100 /home/ubuntu/logs/helios.log"

   # Local
   Check BashOutput for main.py process
   ```

4. **Browser Console**
   - Open Developer Tools (F12)
   - Check Console tab for errors
   - Check Network tab for failed requests
   - Check for repeated errors

---

## Common Mistakes to Avoid

### ❌ What NOT To Do:

1. **Don't assume code works** - "It compiles" ≠ "It works"
2. **Don't skip testing** - "Fast broken code" wastes more time than "slow working code"
3. **Don't rely on user feedback** - Find errors before user sees them
4. **Don't test only APIs** - Test actual user experience
5. **Don't ignore available logs** - Check BashOutput, debug endpoints, server logs
6. **Don't create new files without testing** - Test imports immediately
7. **Don't deploy without verification** - One curl test can save hours

### ✅ What TO Do:

1. **Test immediately** - Run Level 1 tests right after writing code
2. **Check all data sources** - Logs, BashOutput, debug endpoints
3. **Test from user POV** - Open dashboard, click buttons, verify it works
4. **Create monitoring** - Add error tracking and activity logging
5. **Report proactively** - Tell user about problems you found and fixed
6. **Document testing** - Create test reports showing what was verified
7. **Never claim "complete"** - Without proof via testing

---

## Testing Checklist Template

```markdown
## Testing Report for [Feature Name]

### Level 1: Code Verification ✓
- [x] Import test passed
- [x] API endpoint responds: HTTP 200
- [x] BashOutput checked: No errors
- [x] Response structure valid

### Level 2: User Perspective ✓
- [x] Debug endpoints checked: 0 errors
- [x] Dashboard opened: No console errors
- [x] User workflow tested: [describe workflow]
- [x] Data displays correctly

### Level 3: Integration ✓
- [x] End-to-end test passed
- [x] Error handling verified
- [x] Performance acceptable (<500ms)
- [x] Mode switching works (if applicable)

### Issues Found & Fixed:
1. [Issue 1] - Fixed by [solution]
2. [Issue 2] - Fixed by [solution]

### Verification:
- API Test: `curl http://localhost:8100/api/endpoint` → HTTP 200 ✓
- Debug Check: `curl http://localhost:8100/api/debug/recent-errors` → 0 errors ✓
- User Test: Opened dashboard, verified [specific action] works ✓

**Status: TESTED & VERIFIED - Ready for use**
```

---

## Implementation: How to Use This Skill

### After Writing Any Code:

```bash
# 1. Test imports
python -c "from src.api.routers.my_router import router"

# 2. Check endpoint
curl http://localhost:8100/api/my-endpoint

# 3. Check for errors
curl http://localhost:8100/api/debug/recent-errors | jq '.summary'

# 4. Check BashOutput
# Use BashOutput tool on running server process
```

### Before Claiming "Complete":

1. ✅ All Level 1 tests pass
2. ✅ All Level 2 tests pass
3. ✅ Created testing report
4. ✅ No errors in debug endpoints
5. ✅ User workflow verified

### After Deployment:

1. ✅ Check production logs
2. ✅ Monitor debug endpoints
3. ✅ Verify user can actually use it
4. ✅ Document what was tested

---

## Key Insights from Learning Session

### What Went Wrong:
- Created portfolio.py without testing
- Never verified endpoint actually worked
- Didn't check browser console for errors
- Relied on user to discover problems

### What Was Fixed:
- Created observability infrastructure
- Built error tracking and activity logging
- Added debug endpoints for monitoring
- Committed to 3-level testing standard

### The Core Lesson:
**"If you don't have time to test it right, when will you have time to fix it?"**

Quality > Speed (but test fast to have both)

---

## Success Criteria

### Code is "Complete" When:
✅ All 3 testing levels pass
✅ No errors in debug endpoints
✅ User can actually use the feature
✅ Testing report created
✅ Verified from user perspective

### Code is NOT "Complete" When:
❌ Only tested via API (didn't check user POV)
❌ Didn't check debug endpoints
❌ Didn't verify in browser
❌ Assumed it works without proof
❌ User has to tell you it's broken

---

## Activation Instructions

When this skill is activated:
1. Apply 3-level testing to all new code
2. Check BashOutput after every change
3. Use debug endpoints to verify no errors
4. Test from user perspective before claiming complete
5. Create testing reports for all deployments
6. Never ship code without verification

---

**Remember:** The user is passionate about building the best app. Honor that by ensuring everything you build actually works before they see it.

---

*Created from learnings on 2025-10-23*
*Purpose: Ensure quality through systematic testing*
