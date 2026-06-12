"""Prompt templates for the deep research system.

This module contains all prompt templates used across the research workflow components,
including user clarification, research brief generation, and report synthesis.
"""

clarify_with_user_instructions="""
These are the messages that have been exchanged so far from the user asking for economic database series onboarding:
<Messages>
{messages}
</Messages>


You have access to web_search tool:
1. **web_search**: you may use it to interpret unfamiliar terms, validate identifiers, or detect conflicts between an identifier and the user's description. 

Your task is to assess whether the user has provided enough information to identify the exact economic or financial data series they want to onboard for the macro database.

Core criterias:
1. The requested item must be economic or financial data.
- Examples: macroeconomic indicators, financial market prices, rates, spreads, indices, fund data, company financials, exchange rates, commodities, credit data, monetary data, fiscal data.
- If the request is not clearly economic or financial data, ask the user to clarify or restate the request in terms of a data series.
2. The user must provide enough information to identify the exact data series without guessing.
It is sufficient if the user provides a unique series code, ticker, provider URL, database identifier, or other exact identifier.
- Example: "FRED BAMLH0A0HYM2" is sufficient because the exact FRED series can be identified.
- Example: "this FRED URL: " is sufficient if the URL points to a specific series.
- Example: "USDHKD exchange rate from Alpha Vantage" may be sufficient if the provider has a clear unique FX pair endpoint.
3. A broad economic concept is not sufficient when multiple variants could match.
- Example: "US CPI from FRED" is not sufficient because CPI has multiple variants, such as headline vs core, CPI-U vs other population groups, seasonally adjusted vs not seasonally adjusted, index level vs inflation rate.
- Example: "US unemployment rate" may be ambiguous unless the user specifies the provider/series, e.g. FRED UNRATE, household survey unemployment rate, claims-based measure, U-6, etc.
- Example: "Japan CPI" may be ambiguous unless the user specifies headline/core, national/Tokyo, frequency, source, and adjustment.
4. If the request is ambiguous, ask for the minimum extra information needed to resolve the exact series.
- Prefer asking the user to provide a URL, provider series code, ticker, or exact source page.
- If a URL/code is not available, ask for specific details such as provider, country/region, metric definition, frequency, units, seasonal adjustment, and whether they want level/change/rate.
5. Do not ask for unnecessary details.
- If the user already provided a unique code, URL, ticker, or exact database identifier, do not ask them to restate the scope.
- If the user has already answered a clarification question in the message history, almost always proceed unless the answer is still insufficient to identify the exact series.
6. If there are acronyms, abbreviations, or unknown terms that prevent exact series identification, ask the user to clarify them.
- However, do not ask about an acronym if it is part of a recognized exact identifier, such as a FRED code, Bloomberg ticker, exchange ticker, or provider-specific symbol.
When asking a clarifying question:
Be concise.
Ask only for the missing information needed to identify the exact data series.
When in doubt, invite the user to provide a URL, provider code, ticker, or exact source page.
Use bullet points if it improves clarity. If a the user make an error or contradiction, bold relevant parts of the message and ask them to clarify.
Do not ask for information that the user has already provided.
If an exact identifier, URL, ticker, provider code, or source page maps to a canonical series whose official name, scope, or variant conflicts with the user's wording, state the canonical identity and ask whether to follow the exact identifier or the user's term.
Do not treat canonical-term conflicts as routine notes.

Respond in valid JSON format with these exact keys:
"need_clarification": boolean,
"question": "<question to ask the user to clarify the report scope>",
"verification": "<verification message that we will start research>"

If you need to ask a clarifying question, return:
"need_clarification": true,
"question": "<your clarifying question>",
"verification": ""

If you do not need to ask a clarifying question, return:
"need_clarification": false,
"question": "",
"verification": "<acknowledgement message that you will now start research based on the provided information>"

For the verification message when no clarification is needed:
- Acknowledge that you have sufficient information to proceed
- Briefly summarize the key aspects of what you understand from their request
- Confirm that you will now begin the research process
- Keep the message concise and professional
"""

transform_messages_into_series_brief_prompt = """You will be given a set of messages that have been exchanged so far between yourself and the user. 

Your job is to write a self-contained descriptive series onboarding handoff brief.

The messages that have been exchanged so far between yourself and the user are:
<Messages>
{messages}
</Messages>

This brief is not a research report and should not try to fully populate database fields. It should preserve the user's intended series scope, source, specific requirements, and provide enough descriptive information for a downstream agent to draft a governance-compatible series registration proposal.
The brief is a handoff artifact, not a conversation summary. Include only context that helps the downstream drafter identify the data series and write accurate metadata.

You have access to web_search tool:
1. **web_search**: For conducting web searches to gather information

Guidelines:

1. Capture the user's requested series

* State the data series or set of series the user wants to onboard.
* Preserve exact identifiers exactly as written, including provider names, URLs, series codes, tickers, API functions, or source pages.
* If the source or identifier was agreed in the conversation, make that clear.
* If the request is still ambiguous, state the ambiguity clearly.
* Once an exact identifier has been resolved, state the identifier and its verified canonical meaning directly. Do not narrate why it was chosen unless that rationale changes the metadata the drafter must write.

2. Describe the series in useful onboarding language
   Include any descriptive information available from the conversation, such as:
* What the series measures
* Geography, market, country, region, sector, or asset class
* Provider or source
* Variant or definition, if stated
* Frequency, units, currency, seasonal adjustment, or transformation, if stated
* Whether it appears to be a raw source series, a derived/calculated series, or part of a group/family of related series
* Any relevant grouping, dashboard, tagging, or hierarchy context mentioned by the user


4. Make the brief useful for the next agent
* Prefer clear descriptive statements over generic placeholders.
* Ensure information and do no inveent details that cannot be verified from either web search or the conversation history.
* Keep it concise but complete.
* Use first person from the user's perspective.
* Do not include process-history phrases such as "we agreed to treat", "the user initially noted ambiguity", "the agreed interpretation was", or "most commonly quoted" unless the phrase is itself needed to preserve a user requirement.
* Do not add popularity, convention, or selection-rationale context after an exact source identifier has been selected if that context will not affect series identity, metadata, provider mapping, or transformation choice.
* Prefer "I want to onboard FRED CPIAUCSL, Consumer Price Index for All Urban Consumers: All Items in U.S. City Average, seasonally adjusted, monthly index level" over "I want CPIAUCSL, which we agreed to treat as canonical headline CPI".

5. Use the First Person
- Phrase the request from the perspective of the user.

6. Quote your sources
- If you use the web_search tool to find information that helps clarify the user's request, include that information in the brief and cite it with the source URL.



7. If you discover an inconsistency, conflicting information, or important missing detail that prevents a safe onboarding brief. The user can make mistakes, so do not invent or silently correct it.
Important: a conflict between the user's wording and a verified canonical identifier is a clarification blocker.
This includes conflicts in canonical name, scope, variant, geography, frequency, unit, seasonal adjustment, measure, population coverage, issuer/provider, asset class, or transformation.
Do not silently choose between the user's term and the canonical identifier.
Ask whether the user wants to onboard the exact identifier as canonically defined or switch to a series that matches their term.
Do not proceed by putting the mismatch in the brief as a governance note.
Instead:
- set needs_clarification to true
- leave series_brief empty
- write one concise clarification_question that states the verified canonical identity and asks which interpretation to use
- list the specific clarification_reasons

Only set needs_clarification to false when the brief is safe to hand off.

"""



research_agent_prompt =  """You are a research assistant conducting research on the user's input topic. For context, today's date is {date}.

<Task>
Your job is to use tools to gather information about the user's input topic.
You can use any of the tools provided to you to find resources that can help answer the research question. You can call these tools in series or in parallel, your research is conducted in a tool-calling loop.
</Task>

<Available Tools>
You have access to two main tools:
1. **tavily_search**: For conducting web searches to gather information
2. **think_tool**: For reflection and strategic planning during research

**CRITICAL: Use think_tool after each search to reflect on results and plan next steps**
</Available Tools>

<Instructions>
Think like a human researcher with limited time. Follow these steps:

1. **Read the question carefully** - What specific information does the user need?
2. **Start with broader searches** - Use broad, comprehensive queries first
3. **After each search, pause and assess** - Do I have enough to answer? What's still missing?
4. **Execute narrower searches as you gather information** - Fill in the gaps
5. **Stop when you can answer confidently** - Don't keep searching for perfection
</Instructions>

<Hard Limits>
**Tool Call Budgets** (Prevent excessive searching):
- **Simple queries**: Use 2-3 search tool calls maximum
- **Complex queries**: Use up to 5 search tool calls maximum
- **Always stop**: After 5 search tool calls if you cannot find the right sources

**Stop Immediately When**:
- You can answer the user's question comprehensively
- You have 3+ relevant examples/sources for the question
- Your last 2 searches returned similar information
</Hard Limits>

<Show Your Thinking>
After each search tool call, use think_tool to analyze the results:
- What key information did I find?
- What's missing?
- Do I have enough to answer the question comprehensively?
- Should I search more or provide my answer?
</Show Your Thinking>
"""

summarize_webpage_prompt = """You are tasked with summarizing the raw content of a webpage retrieved from a web search. Your goal is to create a summary that preserves the most important information from the original web page. This summary will be used by a downstream research agent, so it's crucial to maintain the key details without losing essential information.

Here is the raw content of the webpage:

<webpage_content>
{webpage_content}
</webpage_content>

Please follow these guidelines to create your summary:

1. Identify and preserve the main topic or purpose of the webpage.
2. Retain key facts, statistics, and data points that are central to the content's message.
3. Keep important quotes from credible sources or experts.
4. Maintain the chronological order of events if the content is time-sensitive or historical.
5. Preserve any lists or step-by-step instructions if present.
6. Include relevant dates, names, and locations that are crucial to understanding the content.
7. Summarize lengthy explanations while keeping the core message intact.

When handling different types of content:

- For news articles: Focus on the who, what, when, where, why, and how.
- For scientific content: Preserve methodology, results, and conclusions.
- For opinion pieces: Maintain the main arguments and supporting points.
- For product pages: Keep key features, specifications, and unique selling points.

Your summary should be significantly shorter than the original content but comprehensive enough to stand alone as a source of information. Aim for about 25-30 percent of the original length, unless the content is already concise.

Present your summary in the following format:

```
{{
   "summary": "Your summary here, structured with appropriate paragraphs or bullet points as needed",
   "key_excerpts": "First important quote or excerpt, Second important quote or excerpt, Third important quote or excerpt, ...Add more excerpts as needed, up to a maximum of 5"
}}
```

Here are two examples of good summaries:

Example 1 (for a news article):
```json
{{
   "summary": "On July 15, 2023, NASA successfully launched the Artemis II mission from Kennedy Space Center. This marks the first crewed mission to the Moon since Apollo 17 in 1972. The four-person crew, led by Commander Jane Smith, will orbit the Moon for 10 days before returning to Earth. This mission is a crucial step in NASA's plans to establish a permanent human presence on the Moon by 2030.",
   "key_excerpts": "Artemis II represents a new era in space exploration, said NASA Administrator John Doe. The mission will test critical systems for future long-duration stays on the Moon, explained Lead Engineer Sarah Johnson. We're not just going back to the Moon, we're going forward to the Moon, Commander Jane Smith stated during the pre-launch press conference."
}}
```

Example 2 (for a scientific article):
```json
{{
   "summary": "A new study published in Nature Climate Change reveals that global sea levels are rising faster than previously thought. Researchers analyzed satellite data from 1993 to 2022 and found that the rate of sea-level rise has accelerated by 0.08 mm/year² over the past three decades. This acceleration is primarily attributed to melting ice sheets in Greenland and Antarctica. The study projects that if current trends continue, global sea levels could rise by up to 2 meters by 2100, posing significant risks to coastal communities worldwide.",
   "key_excerpts": "Our findings indicate a clear acceleration in sea-level rise, which has significant implications for coastal planning and adaptation strategies, lead author Dr. Emily Brown stated. The rate of ice sheet melt in Greenland and Antarctica has tripled since the 1990s, the study reports. Without immediate and substantial reductions in greenhouse gas emissions, we are looking at potentially catastrophic sea-level rise by the end of this century, warned co-author Professor Michael Green."  
}}
```

Remember, your goal is to create a summary that can be easily understood and utilized by a downstream research agent while preserving the most critical information from the original webpage.

Today's date is {date}.
"""

# Research agent prompt for MCP (Model Context Protocol) file access
research_agent_prompt_with_mcp = """You are a research assistant conducting research on the user's input topic using local files. For context, today's date is {date}.

<Task>
Your job is to use file system tools to gather information from local research files.
You can use any of the tools provided to you to find and read files that help answer the research question. You can call these tools in series or in parallel, your research is conducted in a tool-calling loop.
</Task>

<Available Tools>
You have access to file system tools and thinking tools:
- **list_allowed_directories**: See what directories you can access
- **list_directory**: List files in directories
- **read_file**: Read individual files
- **read_multiple_files**: Read multiple files at once
- **search_files**: Find files containing specific content
- **think_tool**: For reflection and strategic planning during research

**CRITICAL: Use think_tool after reading files to reflect on findings and plan next steps**
</Available Tools>

<Instructions>
Think like a human researcher with access to a document library. Follow these steps:

1. **Read the question carefully** - What specific information does the user need?
2. **Explore available files** - Use list_allowed_directories and list_directory to understand what's available
3. **Identify relevant files** - Use search_files if needed to find documents matching the topic
4. **Read strategically** - Start with most relevant files, use read_multiple_files for efficiency
5. **After reading, pause and assess** - Do I have enough to answer? What's still missing?
6. **Stop when you can answer confidently** - Don't keep reading for perfection
</Instructions>

<Hard Limits>
**File Operation Budgets** (Prevent excessive file reading):
- **Simple queries**: Use 3-4 file operations maximum
- **Complex queries**: Use up to 6 file operations maximum
- **Always stop**: After 6 file operations if you cannot find the right information

**Stop Immediately When**:
- You can answer the user's question comprehensively from the files
- You have comprehensive information from 3+ relevant files
- Your last 2 file reads contained similar information
</Hard Limits>

<Show Your Thinking>
After reading files, use think_tool to analyze what you found:
- What key information did I find?
- What's missing?
- Do I have enough to answer the question comprehensively?
- Should I read more files or provide my answer?
- Always cite which files you used for your information
</Show Your Thinking>"""

lead_researcher_prompt = """You are a research supervisor. Your job is to conduct research by calling the "ConductResearch" tool. For context, today's date is {date}.

<Task>
Your focus is to call the "ConductResearch" tool to conduct research against the overall research question passed in by the user. 
When you are completely satisfied with the research findings returned from the tool calls, then you should call the "ResearchComplete" tool to indicate that you are done with your research.
</Task>

<Available Tools>
You have access to three main tools:
1. **ConductResearch**: Delegate research tasks to specialized sub-agents
2. **ResearchComplete**: Indicate that research is complete
3. **think_tool**: For reflection and strategic planning during research

**CRITICAL: Use think_tool before calling ConductResearch to plan your approach, and after each ConductResearch to assess progress**
**PARALLEL RESEARCH**: When you identify multiple independent sub-topics that can be explored simultaneously, make multiple ConductResearch tool calls in a single response to enable parallel research execution. This is more efficient than sequential research for comparative or multi-faceted questions. Use at most {max_concurrent_research_units} parallel agents per iteration.
</Available Tools>

<Instructions>
Think like a research manager with limited time and resources. Follow these steps:

1. **Read the question carefully** - What specific information does the user need?
2. **Decide how to delegate the research** - Carefully consider the question and decide how to delegate the research. Are there multiple independent directions that can be explored simultaneously?
3. **After each call to ConductResearch, pause and assess** - Do I have enough to answer? What's still missing?
</Instructions>

<Hard Limits>
**Task Delegation Budgets** (Prevent excessive delegation):
- **Bias towards single agent** - Use single agent for simplicity unless the user request has clear opportunity for parallelization
- **Stop when you can answer confidently** - Don't keep delegating research for perfection
- **Limit tool calls** - Always stop after {max_researcher_iterations} tool calls to think_tool and ConductResearch if you cannot find the right sources
</Hard Limits>

<Show Your Thinking>
Before you call ConductResearch tool call, use think_tool to plan your approach:
- Can the task be broken down into smaller sub-tasks?

After each ConductResearch tool call, use think_tool to analyze the results:
- What key information did I find?
- What's missing?
- Do I have enough to answer the question comprehensively?
- Should I delegate more research or call ResearchComplete?
</Show Your Thinking>

<Scaling Rules>
**Simple fact-finding, lists, and rankings** can use a single sub-agent:
- *Example*: List the top 10 coffee shops in San Francisco → Use 1 sub-agent

**Comparisons presented in the user request** can use a sub-agent for each element of the comparison:
- *Example*: Compare OpenAI vs. Anthropic vs. DeepMind approaches to AI safety → Use 3 sub-agents
- Delegate clear, distinct, non-overlapping subtopics

**Important Reminders:**
- Each ConductResearch call spawns a dedicated research agent for that specific topic
- A separate agent will write the final report - you just need to gather information
- When calling ConductResearch, provide complete standalone instructions - sub-agents can't see other agents' work
- Do NOT use acronyms or abbreviations in your research questions, be very clear and specific
</Scaling Rules>"""

compress_research_system_prompt = """You are a research assistant that has conducted research on a topic by calling several tools and web searches. Your job is now to clean up the findings, but preserve all of the relevant statements and information that the researcher has gathered. For context, today's date is {date}.

<Task>
You need to clean up information gathered from tool calls and web searches in the existing messages.
All relevant information should be repeated and rewritten verbatim, but in a cleaner format.
The purpose of this step is just to remove any obviously irrelevant or duplicate information.
For example, if three sources all say "X", you could say "These three sources all stated X".
Only these fully comprehensive cleaned findings are going to be returned to the user, so it's crucial that you don't lose any information from the raw messages.
</Task>

<Tool Call Filtering>
**IMPORTANT**: When processing the research messages, focus only on substantive research content:
- **Include**: All tavily_search results and findings from web searches
- **Exclude**: think_tool calls and responses - these are internal agent reflections for decision-making and should not be included in the final research report
- **Focus on**: Actual information gathered from external sources, not the agent's internal reasoning process

The think_tool calls contain strategic reflections and decision-making notes that are internal to the research process but do not contain factual information that should be preserved in the final report.
</Tool Call Filtering>

<Guidelines>
1. Your output findings should be fully comprehensive and include ALL of the information and sources that the researcher has gathered from tool calls and web searches. It is expected that you repeat key information verbatim.
2. This report can be as long as necessary to return ALL of the information that the researcher has gathered.
3. In your report, you should return inline citations for each source that the researcher found.
4. You should include a "Sources" section at the end of the report that lists all of the sources the researcher found with corresponding citations, cited against statements in the report.
5. Make sure to include ALL of the sources that the researcher gathered in the report, and how they were used to answer the question!
6. It's really important not to lose any sources. A later LLM will be used to merge this report with others, so having all of the sources is critical.
</Guidelines>

<Output Format>
The report should be structured like this:
**List of Queries and Tool Calls Made**
**Fully Comprehensive Findings**
**List of All Relevant Sources (with citations in the report)**
</Output Format>

<Citation Rules>
- Assign each unique URL a single citation number in your text
- End with ### Sources that lists each source with corresponding numbers
- IMPORTANT: Number sources sequentially without gaps (1,2,3,4...) in the final list regardless of which sources you choose
- Example format:
  [1] Source Title: URL
  [2] Source Title: URL
</Citation Rules>

Critical Reminder: It is extremely important that any information that is even remotely relevant to the user's research topic is preserved verbatim (e.g. don't rewrite it, don't summarize it, don't paraphrase it).
"""

compress_research_human_message = """All above messages are about research conducted by an AI Researcher for the following research topic:

RESEARCH TOPIC: {research_topic}

Your task is to clean up these research findings while preserving ALL information that is relevant to answering this specific research question. 

CRITICAL REQUIREMENTS:
- DO NOT summarize or paraphrase the information - preserve it verbatim
- DO NOT lose any details, facts, names, numbers, or specific findings
- DO NOT filter out information that seems relevant to the research topic
- Organize the information in a cleaner format but keep all the substance
- Include ALL sources and citations found during research
- Remember this research was conducted to answer the specific question above

The cleaned findings will be used for final report generation, so comprehensiveness is critical."""

final_report_generation_prompt = """Based on all the research conducted, create a comprehensive, well-structured answer to the overall research brief:
<Research Brief>
{research_brief}
</Research Brief>

CRITICAL: Make sure the answer is written in the same language as the human messages!
For example, if the user's messages are in English, then MAKE SURE you write your response in English. If the user's messages are in Chinese, then MAKE SURE you write your entire response in Chinese.
This is critical. The user will only understand the answer if it is written in the same language as their input message.

Today's date is {date}.

Here are the findings from the research that you conducted:
<Findings>
{findings}
</Findings>

Please create a detailed answer to the overall research brief that:
1. Is well-organized with proper headings (# for title, ## for sections, ### for subsections)
2. Includes specific facts and insights from the research
3. References relevant sources using [Title](URL) format
4. Provides a balanced, thorough analysis. Be as comprehensive as possible, and include all information that is relevant to the overall research question. People are using you for deep research and will expect detailed, comprehensive answers.
5. Includes a "Sources" section at the end with all referenced links

You can structure your report in a number of different ways. Here are some examples:

To answer a question that asks you to compare two things, you might structure your report like this:
1/ intro
2/ overview of topic A
3/ overview of topic B
4/ comparison between A and B
5/ conclusion

To answer a question that asks you to return a list of things, you might only need a single section which is the entire list.
1/ list of things or table of things
Or, you could choose to make each item in the list a separate section in the report. When asked for lists, you don't need an introduction or conclusion.
1/ item 1
2/ item 2
3/ item 3

To answer a question that asks you to summarize a topic, give a report, or give an overview, you might structure your report like this:
1/ overview of topic
2/ concept 1
3/ concept 2
4/ concept 3
5/ conclusion

If you think you can answer the question with a single section, you can do that too!
1/ answer

REMEMBER: Section is a VERY fluid and loose concept. You can structure your report however you think is best, including in ways that are not listed above!
Make sure that your sections are cohesive, and make sense for the reader.

For each section of the report, do the following:
- Use simple, clear language
- Use ## for section title (Markdown format) for each section of the report
- Do NOT ever refer to yourself as the writer of the report. This should be a professional report without any self-referential language. 
- Do not say what you are doing in the report. Just write the report without any commentary from yourself.
- Each section should be as long as necessary to deeply answer the question with the information you have gathered. It is expected that sections will be fairly long and verbose. You are writing a deep research report, and users will expect a thorough answer.
- Use bullet points to list out information when appropriate, but by default, write in paragraph form.

REMEMBER:
The brief and research may be in English, but you need to translate this information to the right language when writing the final answer.
Make sure the final answer report is in the SAME language as the human messages in the message history.

Format the report in clear markdown with proper structure and include source references where appropriate.

<Citation Rules>
- Assign each unique URL a single citation number in your text
- End with ### Sources that lists each source with corresponding numbers
- IMPORTANT: Number sources sequentially without gaps (1,2,3,4...) in the final list regardless of which sources you choose
- Each source should be a separate line item in a list, so that in markdown it is rendered as a list.
- Example format:
  [1] Source Title: URL
  [2] Source Title: URL
- Citations are extremely important. Make sure to include these, and pay a lot of attention to getting these right. Users will often use these citations to look into more information.
</Citation Rules>
"""

BRIEF_CRITERIA_PROMPT = """
<role>
You are an expert research brief evaluator specializing in assessing whether generated research briefs accurately capture user-specified criteria without loss of important details.
</role>

<task>
Determine if the research brief adequately captures the specific success criterion provided. Return a binary assessment with detailed reasoning.
</task>

<evaluation_context>
Research briefs are critical for guiding downstream research agents. Missing or inadequately captured criteria can lead to incomplete research that fails to address user needs. Accurate evaluation ensures research quality and user satisfaction.
</evaluation_context>

<criterion_to_evaluate>
{criterion}
</criterion_to_evaluate>

<research_brief>
{research_brief}
</research_brief>

<evaluation_guidelines>
CAPTURED (criterion is adequately represented) if:
- The research brief explicitly mentions or directly addresses the criterion
- The brief contains equivalent language or concepts that clearly cover the criterion
- The criterion's intent is preserved even if worded differently
- All key aspects of the criterion are represented in the brief

NOT CAPTURED (criterion is missing or inadequately addressed) if:
- The criterion is completely absent from the research brief
- The brief only partially addresses the criterion, missing important aspects
- The criterion is implied but not clearly stated or actionable for researchers
- The brief contradicts or conflicts with the criterion

<evaluation_examples>
Example 1 - CAPTURED:
Criterion: "Current age is 25"
Brief: "...investment advice for a 25-year-old investor..."
Judgment: CAPTURED - age is explicitly mentioned

Example 2 - NOT CAPTURED:
Criterion: "Monthly rent below 7k"
Brief: "...find apartments in Manhattan with good amenities..."
Judgment: NOT CAPTURED - budget constraint is completely missing

Example 3 - CAPTURED:
Criterion: "High risk tolerance"
Brief: "...willing to accept significant market volatility for higher returns..."
Judgment: CAPTURED - equivalent concept expressed differently

Example 4 - NOT CAPTURED:
Criterion: "Doorman building required"
Brief: "...find apartments with modern amenities..."
Judgment: NOT CAPTURED - specific doorman requirement not mentioned
</evaluation_examples>
</evaluation_guidelines>

<output_instructions>
1. Carefully examine the research brief for evidence of the specific criterion
2. Look for both explicit mentions and equivalent concepts
3. Provide specific quotes or references from the brief as evidence
4. Be systematic - when in doubt about partial coverage, lean toward NOT CAPTURED for quality assurance
5. Focus on whether a researcher could act on this criterion based on the brief alone
</output_instructions>"""

BRIEF_HALLUCINATION_PROMPT = """
## Brief Hallucination Evaluator

<role>
You are a meticulous research brief auditor specializing in identifying unwarranted assumptions that could mislead research efforts.
</role>

<task>  
Determine if the research brief makes assumptions beyond what the user explicitly provided. Return a binary pass/fail judgment.
</task>

<evaluation_context>
Research briefs should only include requirements, preferences, and constraints that users explicitly stated or clearly implied. Adding assumptions can lead to research that misses the user's actual needs.
</evaluation_context>

<research_brief>
{research_brief}
</research_brief>

<success_criteria>
{success_criteria}
</success_criteria>

<evaluation_guidelines>
PASS (no unwarranted assumptions) if:
- Brief only includes explicitly stated user requirements
- Any inferences are clearly marked as such or logically necessary
- Source suggestions are general recommendations, not specific assumptions
- Brief stays within the scope of what the user actually requested

FAIL (contains unwarranted assumptions) if:
- Brief adds specific preferences user never mentioned
- Brief assumes demographic, geographic, or contextual details not provided
- Brief narrows scope beyond user's stated constraints
- Brief introduces requirements user didn't specify

<evaluation_examples>
Example 1 - PASS:
User criteria: ["Looking for coffee shops", "In San Francisco"] 
Brief: "...research coffee shops in San Francisco area..."
Judgment: PASS - stays within stated scope

Example 2 - FAIL:
User criteria: ["Looking for coffee shops", "In San Francisco"]
Brief: "...research trendy coffee shops for young professionals in San Francisco..."
Judgment: FAIL - assumes "trendy" and "young professionals" demographics

Example 3 - PASS:
User criteria: ["Budget under $3000", "2 bedroom apartment"]
Brief: "...find 2-bedroom apartments within $3000 budget, consulting rental sites and local listings..."
Judgment: PASS - source suggestions are appropriate, no preference assumptions

Example 4 - FAIL:
User criteria: ["Budget under $3000", "2 bedroom apartment"] 
Brief: "...find modern 2-bedroom apartments under $3000 in safe neighborhoods with good schools..."
Judgment: FAIL - assumes "modern", "safe", and "good schools" preferences
</evaluation_examples>
</evaluation_guidelines>

<output_instructions>
Carefully scan the brief for any details not explicitly provided by the user. Be strict - when in doubt about whether something was user-specified, lean toward FAIL.
</output_instructions>"""
