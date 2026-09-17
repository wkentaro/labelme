# Shape Flag rules provide defaults, not a whitelist

Label-matching rules offer unchecked Shape Flags, while existing Shape Flags and their values belong to the Annotation. Removing a rule or changing a Shape's Label therefore preserves stored Shape Flags: treating the rules as a whitelist would let a user's Settings silently erase another annotator's data.

Changes to the rules apply on subsequent Shape creation, editing, and loading. Changing Settings alone leaves the current Annotation untouched. We accept that a relabeled Shape may retain flags that its new Label would not offer by default; preservation takes precedence over automatic cleanup.
