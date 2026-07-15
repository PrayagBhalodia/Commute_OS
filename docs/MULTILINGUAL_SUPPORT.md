# English And Hinglish Support

This build supports English and Romanized Hinglish only. Examples include
`Ahmedabad se Mumbai jana hai`, `sabse sasta option batao`, and `return bhi
same day rakhna`.

The deterministic layer recognizes common Romanized travel words, route forms,
return intent, luggage, relative dates, and cost/time preferences. It preserves
code-mixed text during Unicode and whitespace normalization. The production
prompt tells the LLM to answer in the user's English or Hinglish style while
remaining concise and asking one necessary question at a time.

Devanagari and additional Indic languages are out of scope by explicit project
choice. Dataset validation rejects Devanagari so unsupported language examples
cannot silently enter training. Romanized language identification is heuristic,
so ambiguous English/code-mixed messages may occasionally need clarification.
