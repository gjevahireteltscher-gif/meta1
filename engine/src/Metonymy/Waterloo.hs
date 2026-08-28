module Metonymy.Waterloo
  ( waterlooTree
  , waterlooContextFor
  ) where

import Metonymy.Contextual
import Metonymy.Types

waterlooTree :: LexicalTree
waterlooTree =
  LexicalApply
          "Pred"
          [ LexicalLeaf (anchor "OpenPN" "waterloo" "Waterloo" 0 8) []
          , LexicalApply
              "Compl"
              [ LexicalLeaf
                  (anchor "Verb" "announce" "announced" 9 18)
                  [Requires (AnyOf [HasSort Animate, HasSort Organization])]
              , LexicalApply
                  "ModIn"
                  [ LexicalLeaf
                      (anchor "Noun" "programme" "programme" 25 34)
                      []
                  , LexicalLeaf
                      (anchor "Noun" "physics" "physics" 38 45)
                      [RequiresRelation Conducts physics]
                  ]
              ]
          ]

anchor :: String -> String -> String -> Int -> Int -> LexicalAnchor
anchor constructor lemma surface start end =
  LexicalAnchor constructor lemma surface start end

waterlooContextFor :: Snapshot -> Context
waterlooContextFor snapshot =
  Context
    { contextTree = waterlooTree
    , contextSnapshotHash = snapshotHash snapshot
    , contextSource = waterloo
    , contextAction = "announce"
    , contextRole = SubjectHole
    , contextConstraints =
        [ ContextConstraint
            (anchor "Verb" "announce" "announced" 9 18)
            (Requires (AnyOf [HasSort Animate, HasSort Organization]))
            "VerbNet:say-37.7"
        , ContextConstraint
            (anchor "Noun" "physics" "physics" 38 45)
            (RequiresRelation Conducts physics)
            "context-template:programme-in-topic:v1"
        ]
    , contextRuleProvenance =
        [ "VerbNet:say-37.7"
        , "context-template:programme-in-topic:v1"
        ]
    }
waterloo, physics :: EntityId
waterloo = EntityId "Q639408"
physics = EntityId "Q413"
