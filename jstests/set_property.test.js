// Import necessary dependencies
import '@testing-library/jest-dom';
import 'jest-fetch-mock';
import { jest } from '@jest/globals';

const $ = require('jquery');
global.$ = $;

const module = require('../static/planttracer.js');
const set_property = module.set_property

// Mock dependencies
global.$ = require('jquery');
fetchMock.enableMocks();





describe('set_property function', () => {
    const api_key = 'test_api_key';
    const API_BASE = 'https://example.com/';
    const user_id = 'user123';
    const movie_id = 'movie456';
    const property = 'watched';
    const value = 'true';
  
    beforeEach(() => {
      fetch.resetMocks();
      document.body.innerHTML = '<div id="message"></div>';
      global.api_key = api_key;
      global.API_BASE = API_BASE;
      global.list_ready_function = jest.fn();
    });
  
    it('should call fetch with the correct URL and form data', async () => {
      fetch.mockResponseOnce(JSON.stringify({ error: false }));
  
      set_property(user_id, movie_id, property, value);
  
      await new Promise(process.nextTick); // Wait for async code
  
      expect(fetch).toHaveBeenCalledWith(`${API_BASE}api/set-metadata`, expect.objectContaining({
        method: 'POST',
        body: expect.any(FormData),
      }));
      
      const formData = fetch.mock.calls[0][1].body;
      expect(formData.get("api_key")).toBe(api_key);
      expect(formData.get("set_user_id")).toBe(user_id);
      expect(formData.get("set_movie_id")).toBe(movie_id);
      expect(formData.get("property")).toBe(property);
      expect(formData.get("value")).toBe(value);
    });
  
    it('should display error message if API response has an error', async () => {
      const errorMessage = 'Invalid data';
      fetch.mockResponseOnce(JSON.stringify({ error: true, message: errorMessage }));
  
      set_property(user_id, movie_id, property, value);
  
      await new Promise(process.nextTick); // Wait for async code
  
      expect(document.getElementById('message').innerHTML).toBe(`error: ${errorMessage}`);
    });
  
    it('should call list_ready_function if API response has no error', async () => {
      fetch.mockResponseOnce(JSON.stringify({ error: false }));
  
      set_property(user_id, movie_id, property, value);
  
      await new Promise(process.nextTick); // Wait for async code
  
      expect(global.list_ready_function).toHaveBeenCalledTimes(0);
    });
  
    it('should catch and log errors on fetch failure', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
      fetch.mockReject(() => Promise.reject("API Failure"));
  
      set_property(user_id, movie_id, property, value);
  
      await new Promise(process.nextTick); // Wait for async code
  
      expect(consoleSpy).toHaveBeenCalledWith("API Failure");
      consoleSpy.mockRestore();
    });
  });
  