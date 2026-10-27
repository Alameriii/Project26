                                    Phase 4&5 Sequance Context and DFD


1. Context Digram:
  Process 0 is the whole system. Each arrow is data that an external entity sends to thr system
  or gets back from it.
  
  (context digram)



2. Data Flow Digram(DFD)

<img width="2379" height="1646" alt="dfd drawio" src="https://github.com/user-attachments/assets/916503af-36bf-4212-b24f-3a72fa081e54" />


3. Sequance Digrams
  UC-1: log in 

  A successful login, then three ways it can fail: a wrong password, a lock after five wrong tries,
  and a deactivates account. The note at the bottom shows the 30-minute idle logout. 

  (Sequance digram)

  UC-2: Register Asset

  The backend asks the AI service to classify the asset(UC-3). If the AI is down, the user picks a
  category by hand. A missing or invaild feild stops the save.
  . . . . 


  UC-3: Classify Assest with AI

  This use case runs inside UC-2. the backend sends the asset text to Gemini, get back a category,
  tags and a list of missing fields, and logs the suggestion together with what the user decided.

    (sequence Digram)

  UC-4: Publish Surplus Asset

  An asset under maintenance or waiting for disposal can not be published. Otherwise it goes on the
  marketplace and requesters with a match score of 0.75 or more get a notification.

  UC-5: Search Assets

  Search only reads data. The user can change filters, open an asset, or get a "No matching assets"
  message.

  UC-6: Submit Resource Request 

  The request runs the AI matching in UC-7. If Gemini fails or takes longer than 10 seconds, keyword
  results are shown instead. The asset is reserved for 3 working days, or the request joins a queue if
  the asset is already reserved.

  UC-8: Review Request 

  The representative approves or rejects the request. The system blocks the self-approval (BR-3), adds and administrator     step for assets above the value limit, and marks the request Expired if the reservation ran out.

  UC-9: Record Transfer 

  Two actors take part. The sending representative dispatches the assets and the receiving custodian confirms it arrived.    If it arrives damaged or missing, the transfer becomes disputed.

UC-10: Record Maintenance
After inspection the job ends one of three ways: repaired, no fault found, or not repairable. Not repairable calls UC-12 for an ai recommendation.

UC-11: Process End-of-Life Action
The representative proposes a donation, recycling or disposal, and the sustainability officer decides. A hazardous asset cant be approved until a safety inspection is on record.



  UC-15: Manage users and roles

  The administrator can edit or create a user, deactivate an account, or edit departments, locations and categories.

  UC-16: Edit Asset

  Old values are kept in the asset history. Status changes that the life-cycle rules don't allow are refused.

  UC-17: Withdraw Listing
  Withdraw is blocked while the asset has an approved request. When it goes through, everyone waiting in the queue is        notified.

  UC-18: Track or Cancel Request 

  The requester can see status and history, and can cancel a request only while it is Submitted or 
  Under Review.
  
UC-19: Report Defect
Reporting a defect open maintenance job, set the asset to under Maintenance, pauses its listing if it has one, and notifies maintenance staff.

UC-20: view asset history
The timeline is read-only. Requesters dont see cost or value fields.

UC-21: view Audit log
THE ADMINISTRATOR FILTERS the log and can export it as CSV. Opening the log is itself recorded.

UC-22 : generate Operational Report
Standard report come straight from the database and can be exported as PDF or CSV
