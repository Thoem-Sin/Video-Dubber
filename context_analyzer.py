# context_analyzer.py
"""
Movie Story Context & Character Relational Pronoun Analyzer for Khmer Dubbing.
Analyzes full movie transcripts to determine character relationships (husband/wife, parent/child, friends, formal)
and maps pronouns like 'you' / 'I' to culturally accurate Khmer terms (បង, អូន, ម៉ាក់, ប៉ា, កូន, លោក, អ្នក, ឯង).
"""

import re
import json

RELATIONSHIP_PRESETS = {
    "auto": {
        "name": "Auto-Detect Movie Story & Relationships (AI)",
        "description": "Automatically analyzes full movie dialogue to infer character roles and relationships."
    },
    "couple": {
        "name": "Romantic Couple (Husband & Wife / Lovers - បង & អូន)",
        "description": "Older male / husband is 'បង', younger female / wife is 'អូន'.",
        "male_to_female": {"i": "បង", "you": "អូន", "my": "របស់បង", "your": "របស់អូន"},
        "female_to_male": {"i": "អូន", "you": "បង", "my": "របស់អូន", "your": "របស់បង"},
        "default": {"i": "ខ្ញុំ", "you": "បង", "you_female": "អូន"}
    },
    "family_parent_child": {
        "name": "Family: Parent & Child (ម៉ាក់ / ប៉ា & កូន)",
        "description": "Parent uses 'ម៉ាក់/ប៉ា' for 'I' and 'កូន' for 'you'. Child uses 'កូន' for 'I' and 'ម៉ាក់/ប៉ា' for 'you'.",
        "parent_to_child": {"i": "ម៉ាក់", "you": "កូន"},
        "child_to_parent": {"i": "កូន", "you": "ម៉ាក់"},
        "default": {"i": "ខ្ញុំ", "you": "កូន"}
    },
    "friends": {
        "name": "Close Friends / Peers (ឯង & ខ្ញុំ / អញ)",
        "description": "Informal friendly dialogue among peers.",
        "default": {"i": "ខ្ញុំ", "you": "ឯង"}
    },
    "formal": {
        "name": "Formal / Professional (លោក & អ្នក)",
        "description": "Polite business or public dialogue.",
        "default": {"i": "ខ្ញុំ", "you": "លោក"}
    }
}

class StoryContextAnalyzer:
    def __init__(self):
        pass

    def analyze_story_context(self, segments, llm_fn=None):
        """
        Analyze full transcript to detect story genre, character count, and relationship dynamic.
        Uses Groq Llama 3.3 70B / Gemini AI when available for whole-segment smart context analysis.
        """
        if llm_fn and segments:
            try:
                # Sample lines across whole transcript (beginning, middle, end) for complete story context
                n = len(segments)
                if n <= 40:
                    sample_segs = segments
                else:
                    sample_segs = segments[:15] + segments[n//2 - 10 : n//2 + 10] + segments[-15:]

                sample_lines = [seg.get("original_text", "") for seg in sample_segs if seg.get("original_text")]
                transcript_sample = "\n".join(sample_lines[:45])
                
                analysis_prompt = (
                    "You are an expert film and video story context analyzer.\n"
                    "Analyze the following full movie transcript digest and classify the character relationship dynamic.\n\n"
                    f"TRANSCRIPT DIGEST (WHOLE VIDEO SAMPLING):\n{transcript_sample}\n\n"
                    "CLASSIFICATION CATEGORIES:\n"
                    "1. 'couple': Romantic partners, husband & wife, lovers (Uses male 'បង', female 'អូន')\n"
                    "2. 'family_parent_child': Parents & children (Uses 'ម៉ាក់/ប៉ា', 'កូន')\n"
                    "3. 'friends': Close peers, informal dialogue (Uses 'ឯង', 'ខ្ញុំ')\n"
                    "4. 'formal': Professional, business, public, official dialogue (Uses 'លោក', 'អ្នក')\n\n"
                    "Respond with ONLY a JSON object with these exact keys:\n"
                    '{"relationship": "couple" | "family_parent_child" | "friends" | "formal", "summary": "Short 1-sentence narrative context summary", "character_roles": "Brief description of main character roles"}\n'
                )
                
                res = llm_fn(analysis_prompt)
                if res:
                    clean = re.sub(r'```(?:json)?', '', res).strip('` \n')
                    f_idx = clean.find('{')
                    l_idx = clean.rfind('}')
                    if f_idx != -1 and l_idx != -1:
                        parsed = json.loads(clean[f_idx:l_idx+1])
                        rel = parsed.get("relationship", "").lower()
                        if rel in RELATIONSHIP_PRESETS and rel != "auto":
                            return {
                                "detected_relationship": rel,
                                "relationship_name": RELATIONSHIP_PRESETS[rel].get("name", "Story Dynamic"),
                                "summary": f"[Smart Groq AI Analysis] {parsed.get('summary', 'Story context identified by Groq Llama 3.3 70B.')}",
                                "character_roles": parsed.get("character_roles", ""),
                                "total_segments": len(segments),
                                "pronoun_rules": {
                                    "you_male_target": "បង",
                                    "you_female_target": "អូន",
                                    "you_child_target": "កូន",
                                    "you_parent_target": "ម៉ាក់ / ប៉ា"
                                }
                            }
            except Exception as err:
                print(f"[StoryContextAnalyzer] LLM whole-story analysis pass notice: {err}")

        # Fallback to heuristic keyword detection
        full_text = " ".join([seg.get("original_text", "").lower() for seg in segments])
        
        # Romantic / Couple keywords
        love_keywords = ["love", "honey", "darling", "sweetheart", "babe", "marry", "wife", "husband", "kiss", "hug", "miss you"]
        love_score = sum(full_text.count(kw) for kw in love_keywords)
        
        # Family keywords
        family_keywords = ["mom", "mother", "dad", "father", "son", "daughter", "kid", "baby", "parents", "child", "family"]
        family_score = sum(full_text.count(kw) for kw in family_keywords)

        # Work / Formal keywords
        formal_keywords = ["sir", "boss", "company", "doctor", "police", "officer", "client", "mr", "mrs", "department"]
        formal_score = sum(full_text.count(kw) for kw in formal_keywords)

        # Determine dominant dynamic
        detected_relationship = "couple" # Default for movies
        summary_text = "Romantic / Drama Story Context detected."
        
        if family_score > love_score and family_score > formal_score:
            detected_relationship = "family_parent_child"
            summary_text = f"Family Context detected (keywords count: {family_score}). Using parent/child honorifics (ម៉ាក់/ប៉ា, កូន)."
        elif formal_score > love_score and formal_score > family_score:
            detected_relationship = "formal"
            summary_text = f"Formal / Professional Context detected (keywords count: {formal_score}). Using polite honorifics (លោក, អ្នក)."
        elif love_score > 0:
            detected_relationship = "couple"
            summary_text = f"Romantic / Couple Context detected (keywords count: {love_score}). Using affectionate Khmer terms (បង, អូន)."
        else:
            detected_relationship = "couple"
            summary_text = "General Story Context analyzed. Applied natural relational Khmer pronouns (បង / អូន / ខ្ញុំ)."

        analysis_report = {
            "detected_relationship": detected_relationship,
            "relationship_name": RELATIONSHIP_PRESETS.get(detected_relationship, {}).get("name", "Couple Dynamic"),
            "summary": summary_text,
            "total_segments": len(segments),
            "pronoun_rules": {
                "you_male_target": "បង",
                "you_female_target": "អូន",
                "you_child_target": "កូន",
                "you_parent_target": "ម៉ាក់ / ប៉ា"
            }
        }
        
        return analysis_report

    def refine_khmer_pronouns(self, segments, relationship_mode="auto", analysis_report=None):
        """
        Post-process raw translated Khmer segments to replace generic 'អ្នក' (you) or 'ខ្ញុំ' (I)
        with contextually accurate Khmer pronouns (បង, អូន, ម៉ាក់, ប៉ា, កូន, លោក) based on movie context.
        """
        if relationship_mode == "auto":
            rel_key = analysis_report.get("detected_relationship", "couple") if analysis_report else "couple"
        else:
            rel_key = relationship_mode

        preset = RELATIONSHIP_PRESETS.get(rel_key, RELATIONSHIP_PRESETS["couple"])

        for seg in segments:
            text = seg.get("translated_text", "")
            orig = seg.get("original_text", "").lower()
            
            if rel_key == "couple":
                # If segment original text mentions honey/darling/babe/love or wife/husband
                if any(w in orig for w in ["love", "honey", "darling", "babe", "sweetheart", "miss you"]):
                    # Replace generic 'អ្នក' with 'អូន' or 'បង'
                    text = re.sub(r'\bអ្នក\b', 'អូន', text)
                    text = re.sub(r'\bឯង\b', 'អូន', text)
                else:
                    # In Khmer couple speech, generic 'you' is translated as 'បង' (to male) or 'អូន' (to female)
                    text = re.sub(r'\bអ្នក\b', 'បង', text)
                    
            elif rel_key == "family_parent_child":
                if any(w in orig for w in ["mom", "mother", "mama"]):
                    text = re.sub(r'\bអ្នក\b', 'ម៉ាក់', text)
                    text = re.sub(r'\bខ្ញុំ\b', 'កូន', text)
                elif any(w in orig for w in ["dad", "father", "papa"]):
                    text = re.sub(r'\bអ្នក\b', 'ប៉ា', text)
                    text = re.sub(r'\bខ្ញុំ\b', 'កូន', text)
                elif any(w in orig for w in ["son", "daughter", "child", "kid", "baby"]):
                    text = re.sub(r'\bអ្នក\b', 'កូន', text)
                    text = re.sub(r'\bខ្ញុំ\b', 'ម៉ាក់', text)
                else:
                    text = re.sub(r'\bអ្នក\b', 'កូន', text)

            elif rel_key == "friends":
                text = re.sub(r'\bអ្នក\b', 'ឯង', text)
                
            elif rel_key == "formal":
                text = re.sub(r'\bឯង\b', 'លោក', text)

            seg["translated_text"] = text

        return segments
