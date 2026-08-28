module Metonymy.GF
  ( linearize
  , parseEnglish
  ) where

import Data.Char (isSpace)
import System.Exit (ExitCode (..))
import System.Process (readProcessWithExitCode)

linearize :: FilePath -> String -> IO (Either String String)
linearize pgfPath expression = do
  (exitCode, stdoutText, stderrText) <-
    readProcessWithExitCode
      "gf"
      ["--run", pgfPath]
      ("l -lang=GeneratedMetonymyEng " <> expression <> "\n")
  pure $
    case exitCode of
      ExitSuccess -> Right (trim stdoutText)
      ExitFailure _ -> Left (trim stderrText)

parseEnglish :: FilePath -> String -> IO (Either String [String])
parseEnglish pgfPath sentence = do
  (exitCode, stdoutText, stderrText) <-
    readProcessWithExitCode
      "gf"
      ["--run", pgfPath]
      ("p -lang=GeneratedMetonymyEng \"" <> sentence <> "\"\n")
  pure $
    case exitCode of
      ExitSuccess -> Right (filter (not . null) (map trim (lines stdoutText)))
      ExitFailure _ -> Left (trim stderrText)

trim :: String -> String
trim = dropWhileEnd isSpace . dropWhile isSpace
  where
    dropWhileEnd predicate = reverse . dropWhile predicate . reverse
