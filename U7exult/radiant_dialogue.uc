/*
 * Radiant Dialogue System for Exult
 * Implements NPC-to-NPC barks with cooldowns and structured conversation.
 */

const int COOLDOWN_MINUTES = 10;
const int SEARCH_DIST = 5;
const int PROXIMITY_LIMIT = 4; // Tiles

// Property name for cooldown tracking: "last_bark_time"
// Property name for cooldown tracking: "last_bark_time"
// Note: UCC doesn't support string constants, so we use the literal inline

// Helper to get current time in minutes
var GetCurrentTimeMinutes() {
    return UI_game_day() * 1440 + UI_game_hour() * 60 + UI_game_minute();
}

// Helper to pick a random string from a list
var PickRandom(var list, var count) {
    if (count <= 0) {
        return "...";
    }
    var idx = UI_get_random(count);
    return list[idx];
}

// Dialogue Lists
var GetGreeting(var npc) {
    var list = ["Hail.", "Greetings.", "Well met.", "Good day.", "Hello."];
    return PickRandom(list, 5);
}

var GetFarewell(var npc) {
    var list = ["Farewell.", "Good journey.", "Until next time.", "Bye.", "Be well."];
    return PickRandom(list, 5);
}

var GetInitiation(var npc) {
    var list = ["Nice weather today.", "Heard any rumors?", "Quiet day, isn't it?", "How goes it?", "Seen anything strange?"];
    return PickRandom(list, 5);
}

var GetResponse(var npc) {
    var list = ["Indeed.", "Cove is grody as fuck!", "The Fellowship is strong lately!", "The Gargoyles have their own city now.", "The mages have all gone mad!", "Not recently."];
    return PickRandom(list, 6);
}

// Main Function to be called by NPC schedule or timer
void RadiantBarkCheck(var npc) {
    if (!UI_is_npc(npc)) {
        return;
    }
    if (UI_is_dead(npc)) {
        return;
    }
    
    // Don't let Avatar or party members initiate dialogue
    if (npc == UI_get_avatar_ref()) {
        return;
    }
    var party = UI_get_party_list();
    if (npc in party) {
        return;
    }
    
    if (UI_in_combat()) {
        return; // Don't chat in combat
    }
    // Better NPC combat check:
    if (UI_get_schedule_type(npc) == 0) {
        return; // 0 = IN_COMBAT
    }

    // 1. Cooldown Check
    var currentTime = GetCurrentTimeMinutes();
    var lastBark = UI_get_npc_prop(npc, "last_bark_time");
    
    // Handle day wrapping (simple check) or just absolute difference
    if (currentTime < lastBark) { // New day or time reset
        lastBark = 0; 
    }
    
    if ((currentTime - lastBark) < COOLDOWN_MINUTES) {
        return;
    }

    // 2. Find nearby NPCs
    var nearby = UI_find_nearby(npc, -359, SEARCH_DIST, 4); // 4 = MASK_NPC
    
    var target = 0;
    var candidate;
    var index;
    var max;
    
    // Iterate using UCC for-in syntax
    for (candidate in nearby with index to max) {
        if (candidate == npc) {
            continue;
        }
        if (candidate == -356) {
            continue; // Avatar
        }
        if (UI_is_dead(candidate)) {
            continue;
        }
        if (UI_get_schedule_type(candidate) == 0) {
            continue; // In combat
        }
        if (UI_get_npc_prop(candidate, "ASLEEP")) {
            continue;
        }
        
        // Check target cooldown too
        var targetLastBark = UI_get_npc_prop(candidate, "last_bark_time");
        if ((currentTime - targetLastBark) < COOLDOWN_MINUTES) {
            continue;
        }

        target = candidate;
        break; // Found one
    }

    if (target == 0) {
        return;
    }

    // 3. Execute Conversation
    
    // Update cooldowns
    UI_set_npc_prop(npc, "last_bark_time", currentTime);
    UI_set_npc_prop(target, "last_bark_time", currentTime);

    // Check if they need to approach each other
    var distance = UI_get_distance(npc, target);
    
    // Face each other
    var dirToTarget = UI_find_direction(npc, target);
    var dirToNpc = UI_find_direction(target, npc);

    // Get Lines
    var greeting1 = GetGreeting(npc);
    var greeting2 = GetGreeting(target);
    var init = GetInitiation(npc);
    var resp = GetResponse(target);
    var bye1 = GetFarewell(npc);
    var bye2 = GetFarewell(target);

    // If they're far apart (> 3 tiles), make them approach
    if (distance > 3) {
        // NPC Script - approach then talk
        script npc {
            nohalt;
            face dirToTarget;
            step dirToTarget;
            step dirToTarget;
            wait 10;
            say greeting1;
            wait 20;
            wait 20;
            say init;
            wait 20;
            wait 20;
            say bye1;
        };

        // Target Script - approach then respond
        script target {
            nohalt;
            face dirToNpc;
            step dirToNpc;
            step dirToNpc;
            wait 10;
            wait 20;
            say greeting2;
            wait 20;
            wait 20;
            say resp;
            wait 20;
            say bye2;
        };
    } else {
        // They're close - just talk
        // NPC Script
        script npc {
            nohalt;
            face dirToTarget;
            say greeting1;
            wait 20;
            wait 20;
            say init;
            wait 20;
            wait 20;
            say bye1;
        };

        // Target Script
        script target {
            nohalt;
            face dirToNpc;
            wait 20;
            say greeting2;
            wait 20;
            wait 20;
            say resp;
            wait 20;
            say bye2;
        };
    }
}

// Pulse function - does one scan of nearby NPCs
void DoPulse() {
    var avatar = UI_get_avatar_ref();
    var nearby = UI_find_nearby(avatar, -359, 20, 4);
    var npc;
    var index;
    var max;
    
    for (npc in nearby with index to max) {
        RadiantBarkCheck(npc);
    }
}

// Helper shape function that scripts can call
void PulseHelper shape#(0x1) () {
    DoPulse();
    
    // Schedule next pulse (increased to 250 ticks = ~10 seconds to reduce lag)
    var avatar = UI_get_avatar_ref();
    script avatar after 250 ticks {
        nohalt;
        call PulseHelper;
    };
}

// Global Controller - starts the system
void StartRadiantSystem() {
    DoPulse(); // Run immediately
    
    // Then schedule the repeating loop (250 ticks = ~10 seconds)
    var avatar = UI_get_avatar_ref();
    script avatar after 250 ticks {
        nohalt;
        call PulseHelper;
    };
}

// Activator Item Script
// Shape 1030 (0x406)
// Double-click to start the system
void ActivatorItem shape#(0x406) () {
    if (event == DOUBLECLICK) {
        StartRadiantSystem();
        UI_item_say(item, "Radiant Dialogue System Activated.");
    }
}
